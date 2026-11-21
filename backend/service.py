"""SenFund core: invoices, receipt verification, reorg recheck, reconciliation, simulated conversion/payout."""
import hashlib
import html
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from eth_account import Account
from web3 import Web3

from . import chain, ens
from .adapters import CORRIDORS, MockConversion, MockRemittance, ProviderTimeout
from .config import web3_for
from .db import DB
from .state import InvalidTransition, transition


RECONCILE_BLOCKS = 500



def advisor_line(quote: dict, decision: str) -> str:
    """Plain-English status line for a payout decision: success, fallback or hold."""
    amt = f"{quote['amount']} {quote['currency']} (simulated)"
    return {
        "success": f"Your payout of {amt} is complete.",
        "fallback": f"Your payout of {amt} is going via Protected P2P fallback. Your USDT stays locked until your bank confirms the credit (simulated).",
        "hold": f"Your payout of {amt} is on hold. The provider may have accepted the order, so we are checking before doing anything else.",
    }[decision]

def draft_note(payer: str, amount: str, description: str, key=None) -> str:
    """Draft a short invoice note for the payer. Uses Claude when ANTHROPIC_API_KEY is set, else a fixed template."""
    fallback = f"Hi {payer}, please find the invoice for {description}: {amount} USDT. Thank you."
    key = key if key is not None else os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return fallback
    import urllib.request
    prompt = (f"Write a polite two-sentence invoice note to {payer} for {description}, amount {amount} USDT. "
              "Do not promise payout times or exchange rates. Plain text only.")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        data=json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 200,
                         "messages": [{"role": "user", "content": prompt}]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            text = json.load(r)["content"][0]["text"].strip()
        return text or fallback
    except Exception:  # drafting is optional; never block invoicing
        return fallback


class InvoiceCreationConflict(ValueError):
    """A client reused an invoice creation key for different details."""


class SenFund:
    def __init__(self, cfg, w3=None, db=None):
        self.cfg = cfg
        self.w3 = w3 or web3_for(cfg)
        self.db = db or DB(cfg.db_path)
        self.merchant = Account.from_key(cfg.merchant_key).address if cfg.merchant_key else ""

    # ---------- invoices ----------
    def create_invoice(self, usd: str, description: str, customer: str = "",
                       beneficiary: dict | None = None, ttl: int | None = None,
                       idempotency_key: str | None = None, owner: str | None = None,
                       corridor: str = "IN", asset: str = "USDT") -> dict:
        if corridor not in CORRIDORS:
            raise ValueError("Unknown payout corridor.")
        if not (self.cfg.settlement and self.merchant):
            raise ValueError("deployment not configured: need settlement contract and merchant key")
        assets = self.cfg.payment_assets
        if not isinstance(asset, str) or asset not in assets:
            raise ValueError("Choose a supported payment asset.")
        token, decimals = assets[asset]
        try:
            usd_d = Decimal(str(usd))
        except InvalidOperation:
            raise ValueError("Enter a valid invoice amount.") from None
        if (not usd_d.is_finite() or usd_d <= 0 or usd_d.adjusted() >= 22
                or usd_d.as_tuple().exponent < -min(2, decimals)):
            raise ValueError("Enter a positive invoice amount with up to two decimal places and 22 whole digits.")
        numerator, denominator = usd_d.as_integer_ratio()
        units = numerator * 10 ** decimals // denominator
        if units >= 2**256:
            raise ValueError("Invoice amount exceeds the settlement contract limit.")
        if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", idempotency_key):
            raise ValueError("Invalid Idempotency-Key header.")

        scope = f"{self.cfg.env}:{self.cfg.chain_id}:{self.cfg.settlement.lower()}:{self.merchant.lower()}"
        if owner is not None:
            scope = f"{scope}:{owner}"
        data = {"description": description, "customer": customer, "usd": str(usd_d),
                "beneficiary": beneficiary or {}}
        fingerprint = hashlib.sha256(json.dumps(
            # IN keeps the old fingerprint so existing keys still match.
            [units, description, customer, data["beneficiary"], ttl]
            + ([] if corridor == "IN" else [corridor]) + ([] if asset == "USDT" else [asset]), sort_keys=True
        ).encode()).hexdigest()
        if idempotency_key is not None:
            existing = self._invoice_for_key(scope, idempotency_key, fingerprint)
            if existing is not None:
                return existing

        if self.cfg.env == "testnet":
            # ENS lookup is two Sepolia RPC calls; cache 60s so invoice creates don't queue behind it.
            cached = getattr(self, "_ens_cache", None)
            if not cached or time.time() - cached[1] > 60:
                cached = self._ens_cache = (ens.resolve_recipient(self.cfg), time.time())
            recipient = cached[0]
        else:
            recipient = self.cfg.recipient
        if not recipient:
            raise ValueError("recipient not configured")
        inv = "inv_" + uuid.uuid4().hex[:12]
        now = int(time.time())
        req = chain.sign_request({
            "chainId": self.cfg.chain_id, "contract": Web3.to_checksum_address(self.cfg.settlement),
            "invoiceId": "0x" + os.urandom(32).hex(), "merchant": self.merchant,
            "domainName": self.cfg.domain_name, "recipient": Web3.to_checksum_address(recipient),
            "token": Web3.to_checksum_address(token), "amount": str(units),
            "expiry": now + (ttl or self.cfg.invoice_ttl),
        }, self.cfg.merchant_key)
        with self.db.transaction():
            if idempotency_key is not None:
                existing = self._invoice_for_key(scope, idempotency_key, fingerprint)
                if existing is not None:
                    return existing
            self.db.x("insert into invoices(id,invoice_id,created_at,usd,amount_units,data,request,corridor) values(?,?,?,?,?,?,?,?)",
                      inv, req["invoiceId"], now, str(usd_d), str(units), json.dumps(data), json.dumps(req), corridor)
            if owner is not None:
                self.db.x("insert into invoice_owners(invoice,account_id) values(?,?)", inv, owner)
            if idempotency_key is not None:
                self.db.x("insert into invoice_creation_keys(scope,key,fingerprint,invoice) values(?,?,?,?)",
                          scope, idempotency_key, fingerprint, inv)
        return self.get(inv)

    def _invoice_for_key(self, scope, key, fingerprint):
        row = self.db.one("select fingerprint,invoice from invoice_creation_keys where scope=? and key=?", scope, key)
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise InvoiceCreationConflict("This request key is already associated with different invoice details.")
        return self.get(row["invoice"])

    def get(self, inv: str) -> dict:
        r = self.db.one("select * from invoices where id=?", inv)
        if not r:
            raise KeyError(inv)
        r["data"], r["request"] = json.loads(r["data"]), json.loads(r["request"])
        r["asset"] = "WBT" if r["request"]["token"].lower() == self.cfg.wrapped_wbt.lower() else "USDT"
        r["receipt"] = self.db.one("select * from receipts where invoice=? and status='active'", inv)
        r["operations"] = self.db.q("select key,stage,status,external_id,detail from operations where invoice=?", inv)
        r["history"] = self.db.q("select stage,old,new,source,reason,at from transitions where invoice=? order by id", inv)
        return r

    def list(self, owner=None, *, legacy_only=False):
        if legacy_only:
            rows = self.db.q("select i.id from invoices i where not exists "
                             "(select 1 from invoice_owners o where o.invoice=i.id) order by i.created_at desc,i.id desc")
        elif owner is None:
            rows = self.db.q("select id from invoices order by created_at desc,id desc")
        else:
            rows = self.db.q(
                "select i.id from invoices i join invoice_owners o on o.invoice=i.id "
                "where o.account_id=? order by i.created_at desc,i.id desc", owner,
            )
        return [self.get(row["id"]) for row in rows]

    def checkout_request(self, inv: str) -> dict:
        """What the independent checkout needs: the signed request plus public display fields. No beneficiary data."""
        r = self.get(inv)
        asset = r["asset"]
        return {**r["request"], "usd": r["usd"],
                "tokenSymbol": "WWBT (test)" if asset == "WBT" else "USDT (test)",
                "tokenDecimals": self.cfg.payment_assets[asset][1]}

    # ---------- payment ----------
    def submit_tx(self, inv: str, tx_hash: str, source="api") -> dict:
        tx_hash = chain._h(tx_hash.strip().lower())
        if len(tx_hash) != 66 or any(c not in "0123456789abcdef" for c in tx_hash[2:]):
            raise ValueError("bad tx hash")
        r = self.get(inv)
        if r["payment"] == "PAID":
            return {"status": "already_paid", "invoice": r}
        return self._verify_candidate(r, tx_hash, source)

    def verify(self, inv: str, source="verifier") -> dict:
        r = self.get(inv)
        if r["payment"] != "SUBMITTED" or not r["tx_hash"]:
            return {"status": r["payment"].lower(), "invoice": r}
        return self._verify_candidate(r, r["tx_hash"], source)

    def _verify_candidate(self, invoice: dict, tx_hash: str, source: str) -> dict:
        inv = invoice["id"]
        try:
            v = chain.verify_receipt(self.w3, self.cfg, invoice["request"], tx_hash)
        except chain.VerificationError as e:
            with self.db.transaction():
                current = self.get(inv)
                if current["payment"] == "PAID":
                    return {"status": "already_paid", "invoice": current}
                if e.code == "pending":
                    if current["payment"] == "OPEN":
                        transition(self.db, inv, "payment", "SUBMITTED", source, tx_hash)
                        self.db.x("update invoices set tx_hash=? where id=?", tx_hash, inv)
                        current["tx_hash"] = tx_hash
                    if current["tx_hash"] == tx_hash:
                        self.db.x("update invoices set last_reason=? where id=?", str(e), inv)
                    return {"status": "pending", "reason": str(e), "invoice": self.get(inv)}
                if current["payment"] == "SUBMITTED" and current["tx_hash"] == tx_hash:
                    transition(self.db, inv, "payment", "OPEN", source, f"rejected tx {tx_hash}: {e}")
                    self.db.x("update invoices set last_reason=?, tx_hash=null where id=?", str(e), inv)
                return {"status": "rejected", "reason": e.code, "detail": str(e), "invoice": self.get(inv)}

        with self.db.transaction():
            current = self.get(inv)
            if current["payment"] == "PAID":
                return {"status": "already_paid", "invoice": current}
            if current["payment"] not in ("OPEN", "SUBMITTED"):
                return {"status": "rejected", "reason": "invoice_not_open", "invoice": current}
            receipt_key = (self.cfg.chain_id, v["tx_hash"], v["log_index"])
            cur = self.db.x("insert or ignore into receipts(invoice,chain_id,tx_hash,log_index,block_number,block_hash,payer,amount) values(?,?,?,?,?,?,?,?)",
                            inv, *receipt_key, v["block_number"], v["block_hash"], v["payer"], v["amount"])
            if cur.rowcount == 0:
                other = self.db.one("select invoice,status from receipts where chain_id=? and tx_hash=? and log_index=?", *receipt_key)
                if other["invoice"] != inv or other["status"] == "active":
                    return {"status": "rejected", "reason": "duplicate_receipt", "invoice": current}
                self.db.x("update receipts set status='active', block_hash=?, block_number=? where chain_id=? and tx_hash=? and log_index=?",
                          v["block_hash"], v["block_number"], *receipt_key)
            transition(self.db, inv, "payment", "PAID", source, f"verified {v['confirmations']} confs")
            self.db.x("update invoices set tx_hash=?, last_reason=null where id=?", tx_hash, inv)
            return {"status": "paid", "invoice": self.get(inv)}

    def recheck(self) -> list:
        """Only a successfully read replacement block can orphan a confirmed receipt."""
        flagged = []
        for rc in self.db.q("select * from receipts where status='active'"):
            try:
                block_hash = chain._h(self.w3.eth.get_block(rc["block_number"])["hash"])
                if len(block_hash) != 66 or any(c not in "0123456789abcdef" for c in block_hash[2:]):
                    continue
            except Exception:
                continue
            if block_hash == rc["block_hash"]:
                continue
            inv = rc["invoice"]
            with self.db.transaction():
                changed = self.db.x("update receipts set status='orphaned' where id=? and status='active' and block_hash=?",
                                    rc["id"], rc["block_hash"])
                if changed.rowcount != 1:
                    continue
                transition(self.db, inv, "payment", "OPEN", "reorg", f"block {rc['block_number']} replaced")
                r = self.get(inv)
                if r["conversion"] == "PENDING":
                    transition(self.db, inv, "conversion", "FAILED", "reorg", "payment reorged")
                if r["payout"] in ("QUOTED", "SUBMITTED"):
                    transition(self.db, inv, "payout", "ON_HOLD", "reorg", "payment reorged")
                self.db.x("update invoices set needs_review=1, last_reason='reorg_detected', tx_hash=? where id=?",
                          rc["tx_hash"], inv)
                transition(self.db, inv, "payment", "SUBMITTED", "reorg", "awaiting re-inclusion")
            flagged.append(inv)
        return flagged

    def reconcile(self, from_block: int | None = None, *, prioritize_recent: bool = False) -> list:
        """Resume the historical scan and optionally check the latest page first."""
        if self.w3.eth.chain_id != self.cfg.chain_id:
            raise chain.VerificationError("wrong_network", "reconciliation RPC does not match deployment")
        settlement = Web3.to_checksum_address(self.cfg.settlement)
        key = (self.cfg.chain_id, settlement.lower())
        start = self.cfg.from_block if from_block is None else from_block
        if start < 0:
            raise ValueError("from_block must be nonnegative")
        if from_block is None:
            cursor = self.db.one("select block_number,block_hash from reconciliation_cursor where chain_id=? and settlement=?", *key)
            if cursor and cursor["block_number"] >= start:
                anchor = self.w3.eth.get_block(cursor["block_number"])
                if chain._h(anchor["hash"]) == cursor["block_hash"]:
                    start = cursor["block_number"] + 1
        latest = self.w3.eth.block_number - max(1, self.cfg.confirmations) + 1
        end = min(latest, start + RECONCILE_BLOCKS - 1)
        if end < start:
            return []
        recent_start = latest - RECONCILE_BLOCKS + 1
        # The recent page never advances the historical cursor across a gap.
        found = self.reconcile(recent_start) if prioritize_recent and from_block is None and end < recent_start else []
        block_hash = chain._h(self.w3.eth.get_block(end)["hash"])
        logs = self.w3.eth.get_logs({"address": settlement, "fromBlock": start, "toBlock": end,
                                     "topics": [chain._h(chain.SETTLED_TOPIC)]})
        retry_page = False
        for lg in logs:
            r = self.db.one("select id,payment from invoices where invoice_id=?", chain._h(lg["topics"][1]))
            if r and r["payment"] in ("OPEN", "SUBMITTED"):
                res = self.submit_tx(r["id"], chain._h(lg["transactionHash"]), source="reconcile")
                found.append({"invoice": r["id"], "status": res["status"]})
                retry_page |= res["status"] == "pending"
        if from_block is None and not retry_page and block_hash == chain._h(self.w3.eth.get_block(end)["hash"]):
            self.db.x("insert or replace into reconciliation_cursor(chain_id,settlement,block_number,block_hash) values(?,?,?,?)",
                      *key, end, block_hash)
        return found

    # ---------- simulated conversion ----------
    def run_conversion(self, inv: str) -> dict:
        r = self.get(inv)
        if r["asset"] == "WBT":
            raise InvalidTransition("WBT invoices settle in wrapped WBT. Simulated fiat payout is available for USDT invoices.")
        if r["payment"] != "PAID":
            raise InvalidTransition("conversion requires a verified payment")
        if r["conversion"] == "COMPLETED":
            return r
        transition(self.db, inv, "conversion", "PENDING", "conversion")
        res = MockConversion().convert(int(r["amount_units"]), self.cfg.token_decimals)
        self.db.x("insert or replace into operations(key,invoice,stage,status,external_id,detail,at) values(?,?,?,?,?,?,?)",
                  f"{inv}:conversion:{self.cfg.env}", inv, "conversion", "COMPLETED", None, json.dumps(res), int(time.time()))
        transition(self.db, inv, "conversion", "COMPLETED", "conversion", "simulated")
        return self.get(inv)

    # ---------- simulated payout ----------
    def cash_out_intent(self, inv):
        row = self.db.one("select detail from operations where key=?", f"{inv}:cash-out:{self.cfg.env}")
        return json.loads(row["detail"])["corridor"] if row else None

    def check_cash_out_route(self, inv, scenario):
        if self.cash_out_intent(inv) and scenario != "mudrex_unavailable":
            raise InvalidTransition("This invoice is reserved for the selected P2P cash-out.")

    def quote_cash_out(self, inv, corridor):
        if not isinstance(corridor, str) or corridor not in CORRIDORS:
            raise ValueError("Choose a supported payout currency.")
        r = self.get(inv)
        if (r["asset"] != "USDT" or r["payment"] != "PAID" or r["needs_review"] or not r["receipt"]):
            raise InvalidTransition("Cash-out requires a verified test USDT invoice.")
        intent = self.cash_out_intent(inv)
        if intent and intent != corridor:
            raise InvalidTransition("The payout currency is locked for this cash-out.")
        if r["payout"] != "NOT_STARTED" or self.db.one("select 1 from operations where key=?", f"{inv}:payout:{self.cfg.env}"):
            raise InvalidTransition("A payout has already been attempted for this invoice.")
        conversion = self.db.one("select detail from operations where key=?", f"{inv}:conversion:{self.cfg.env}")
        conversion = (json.loads(conversion["detail"]) if conversion else
                      MockConversion().convert(int(r["amount_units"]), self.cfg.token_decimals))
        quote = MockRemittance(self.db, route="p2p", corridor=corridor).quote(conversion["net_usd"])
        if Decimal(quote["amount"]) <= 0:
            raise ValueError("This invoice amount is too small for the selected corridor fees.")
        conversion_fee = Decimal(r["usd"]) - Decimal(conversion["net_usd"])
        return {**quote, "corridor": corridor, "inputUsdt": r["usd"], "conversionFeeUsd": str(conversion_fee)}

    def prepare_cash_out(self, inv, corridor):
        with self.db.transaction():
            intent = self.cash_out_intent(inv)
            if intent and intent == corridor and self.db.one(
                    "select 1 from operations where key=?", f"{inv}:payout:{self.cfg.env}"):
                return False
            self.quote_cash_out(inv, corridor)
            if not intent:
                self.db.x("update invoices set corridor=? where id=?", corridor, inv)
                self.db.x("insert into operations(key,invoice,stage,status,detail,at) values(?,?,?,?,?,?)",
                          f"{inv}:cash-out:{self.cfg.env}", inv, "cash-out", "CONFIRMED",
                          json.dumps({"corridor": corridor}), int(time.time()))
        self.run_conversion(inv)
        return True

    def run_payout(self, inv: str, scenario: str = "success") -> dict:
        r = self.get(inv)
        if r["payment"] != "PAID" or r["conversion"] != "COMPLETED" or r["needs_review"]:
            raise InvalidTransition("payout requires verified payment, completed conversion and no pending review")
        if scenario not in ("success", "hold", "fail", "timeout", "timeout_created", "mudrex_unavailable"):
            raise ValueError("unknown simulated payout scenario")
        if r["payout"] in ("COMPLETED", "FAILED"):
            return r
        self.check_cash_out_route(inv, scenario)
        key = f"{inv}:payout:{self.cfg.env}"
        op = self.db.one("select * from operations where key=?", key)
        if op:
            route = json.loads(op["detail"]).get("route", "legacy")
            provider = MockRemittance(self.db, "hold" if route == "p2p" else scenario, route, r["corridor"])
            if op["external_id"]:
                return self._apply_payout(inv, provider.status(op["external_id"]) or op["status"], "poll")
            found = provider.find_by_key(key)
            if found:
                return self._record_order(inv, key, found, "reconcile")
            if route != "p2p" and scenario == "mudrex_unavailable":
                # An unavailable primary does not resolve an earlier dispatch with an unknown outcome.
                return r
        else:
            fallback = scenario == "mudrex_unavailable"
            c = CORRIDORS[r["corridor"]]
            provider = MockRemittance(self.db, "hold" if fallback else scenario,
                                      c["fallback"] if fallback else c["primary"], r["corridor"])
            conv = json.loads(self.db.one("select detail from operations where key=?", f"{inv}:conversion:{self.cfg.env}")["detail"])
            quote = provider.quote(conv["net_usd"])
            reason = f"{quote['amount']} {quote['currency']} (simulated)"
            if fallback:
                quote["fallback_reason"] = "Licensed provider not available in this demo (requires identity verification). No order was submitted."
                reason += f"; {quote['fallback_reason']}"
            with self.db.transaction():
                transition(self.db, inv, "payout", "QUOTED", provider.route, reason)
                # Record the selected route and idempotency key before dispatch.
                self.db.x("insert into operations(key,invoice,stage,status,external_id,detail,at) values(?,?,?,?,?,?,?)",
                          key, inv, "payout", "DISPATCHING", None, json.dumps(quote), int(time.time()))
            op = self.db.one("select * from operations where key=?", key)
        try:
            order = provider.create(key, json.loads(op["detail"]), r["data"].get("beneficiary", {}))
        except ProviderTimeout as e:
            with self.db.transaction():
                self.db.x("update operations set status='UNKNOWN' where key=?", key)
                if self.get(inv)["payout"] != "ON_HOLD":
                    transition(self.db, inv, "payout", "ON_HOLD", "payout", f"provider timeout ({e}); reconcile before retry")
            return self.get(inv)
        return self._record_order(inv, key, order, "payout")

    def confirm_p2p_credit(self, inv: str) -> dict:
        """Complete the demo P2P order after an explicitly simulated bank credit."""
        key = f"{inv}:payout:{self.cfg.env}"
        with self.db.transaction():
            r = self.get(inv)
            op = self.db.one("select * from operations where key=?", key)
            if not op or json.loads(op["detail"]).get("route") != "p2p" or not op["external_id"]:
                raise InvalidTransition("no simulated P2P order for this invoice")
            if r["payment"] != "PAID" or r["needs_review"]:
                raise InvalidTransition("cannot confirm credit while the payment requires review")
            if r["payout"] == "COMPLETED":
                return r
            provider = MockRemittance(self.db, route="p2p", corridor=r["corridor"])
            if r["payout"] != "ON_HOLD" or not provider.simulate_bank_credit(key, op["external_id"]):
                raise InvalidTransition("the simulated P2P order is not awaiting credit")
            self.db.x("update operations set status='COMPLETED' where key=?", key)
            transition(self.db, inv, "payout", "COMPLETED", "p2p", "simulated bank credit")
            return self.get(inv)

    def _record_order(self, inv, key, order, source):
        with self.db.transaction():
            self.db.x("update operations set external_id=?, status=? where key=?", order["order_id"], order["status"], key)
            if self.get(inv)["payout"] in ("QUOTED", "ON_HOLD") and order["status"] != "ON_HOLD":
                transition(self.db, inv, "payout", "SUBMITTED", source, order["order_id"])
            return self._apply_payout(inv, order["status"], source)

    def _apply_payout(self, inv, status, source):
        cur = self.get(inv)["payout"]
        if status and status != cur:
            try:
                transition(self.db, inv, "payout", status, source)
            except InvalidTransition:
                pass  # stale provider status never moves state backward
        return self.get(inv)

    def provider_callback(self, event_id: str, order_id: str, status: str) -> str:
        if self.db.one("select 1 from adapter_events where event_id=?", event_id):
            return "duplicate"
        op = self.db.one("select * from operations where stage='payout' and external_id=?", order_id)
        outcome = "unknown_order"
        if op and json.loads(op["detail"]).get("route") == "p2p":
            outcome = "wrong_route"
        elif op:
            before = self.get(op["invoice"])["payout"]
            try:
                changed = transition(self.db, op["invoice"], "payout", status, "callback", event_id)
                outcome = "applied" if changed else "noop"
            except InvalidTransition:
                outcome = f"ignored_stale ({before} -> {status})"
        self.db.x("insert into adapter_events(event_id,invoice,payload,outcome,at) values(?,?,?,?,?)",
                  event_id, op and op["invoice"], json.dumps({"order": order_id, "status": status}), outcome, int(time.time()))
        return outcome

    # ---------- export ----------
    def evidence_pack(self, inv: str) -> dict:
        """Owner-facing JSON proof. Allowlisted fields only: no bank details, emails or secrets."""
        r = self.get(inv)
        rc = r["receipt"]
        if r["payment"] != "PAID" or not rc:
            raise InvalidTransition("evidence pack needs a verified payment")
        keep = ("simulated", "gross_usd", "fee_usd", "net_usd", "route", "currency", "rate", "fee", "amount", "fallback_reason")
        ops = [{"stage": o["stage"], "status": o["status"], "providerRef": o["external_id"],
                "detail": {k: v for k, v in json.loads(o["detail"] or "{}").items() if k in keep}} for o in r["operations"]]
        req = r["request"]
        payout = next((o for o in reversed(ops) if o["stage"] == "payout"), None)
        detail = payout["detail"] if payout else {}
        order = payout and payout["providerRef"]
        return {"invoice": inv, "digest": req["digest"], "corridor": r["corridor"],
                "environment": self.cfg.env, "chainId": self.cfg.chain_id, "testnetOnly": True,
                "explorer": f'{self.cfg.explorer}/tx/{rc["tx_hash"]}',
                "settlement": {**{k: rc[k] for k in ("tx_hash", "block_number", "block_hash", "log_index", "payer", "amount")},
                               "recipient": req["recipient"], "token": req["token"], "tokenSymbol": "WWBT (test)" if r["asset"] == "WBT" else "USDT (test)"},
                "payout": {"route": detail.get("route"), "fallbackReason": detail.get("fallback_reason"),
                           "simulatedOrderRef": order,
                           "simulatedBankRef": f"SIM-BANK-{order}" if order and r["payout"] == "COMPLETED" else None},
                "states": {"payment": r["payment"], "conversion": r["conversion"], "payout": r["payout"]},
                "operations": ops, "history": r["history"],
                "note": "Conversion and payout are simulated. No money moved."}

    def receipt_html(self, inv: str) -> str:
        r = self.get(inv)
        rc = r["receipt"]
        req = r["request"]
        ops = {o["stage"]: o for o in r["operations"]}
        conv = json.loads(ops["conversion"]["detail"]) if "conversion" in ops else None
        pay = json.loads(ops["payout"]["detail"]) if "payout" in ops else None

        def e(value):
            return html.escape(str(value))

        def field(label, value, *, address=False):
            shown = f"<code>{e(value)}</code>" if address else e(value)
            return f"<div><dt>{e(label)}</dt><dd>{shown}</dd></div>"

        asset = "WWBT" if r["asset"] == "WBT" else "USDT"
        decimals = self.cfg.payment_assets[r["asset"]][1]
        paid = r["payment"] == "PAID" and rc is not None and not r["needs_review"]
        status = "Paid" if paid else "Under review" if r["needs_review"] else r["payment"].replace("_", " ").title()
        amount = format(Decimal(rc["amount"]).scaleb(-decimals).normalize(), "f") if paid else r["usd"]
        issued = datetime.fromtimestamp(r["created_at"], timezone.utc).strftime("%d %b %Y")
        customer = r["data"].get("customer")
        service = r["data"].get("description") or "Invoice payment"
        network = "Whitechain Sepolia" if self.cfg.env == "testnet" else "Local test network"

        settlement = ""
        if rc:
            tx = rc["tx_hash"]
            explorer = f"{self.cfg.explorer}/tx/{tx}" if self.cfg.explorer else ""
            tx_hash = (f'<a href="{e(explorer)}"><code>{e(tx)}</code></a>'
                       if explorer else f"<code>{e(tx)}</code>")
            settlement = f"""
              <section class="section">
                <h2>Settlement details</h2>
                <dl class="details">
                  {field("Network", f"{network} · {self.cfg.chain_id}")}
                  {field("Block", rc["block_number"])}
                  {field("Paid from", rc["payer"], address=True)}
                  {field("Received by", req["recipient"], address=True)}
                  <div class="wide"><dt>Transaction</dt><dd>{tx_hash}</dd></div>
                </dl>
              </section>"""

        simulation = ""
        if r["asset"] == "USDT" and (conv or pay):
            conversion = ""
            if conv and conv.get("net_usd") is not None:
                fee = f' after a {e(conv["fee_usd"])} USD simulated fee' if conv.get("fee_usd") is not None else ""
                conversion = f'<p>Conversion quote · {e(conv["net_usd"])} USD net{fee}.</p>'
            payout = ""
            if pay:
                labels = {"COMPLETED": "Simulated payout completed", "ON_HOLD": "Simulated payout on hold",
                          "FAILED": "Simulated payout failed"}
                routes = {"mudrex": "Mudrex", "p2p": "Protected P2P fallback", "eu_offramp": "MiCA off-ramp"}
                route = e(routes.get(pay.get("route"), "Mock remittance"))
                quote = (f'{e(pay["amount"])} {e(pay["currency"])} via '
                         if pay.get("amount") is not None and pay.get("currency") else "")
                payout = f'<p><strong>{e(labels.get(r["payout"], r["payout"]))}</strong> · {quote}{route}.</p>'
                reference = ops["payout"]["external_id"]
                if reference:
                    payout += f'<p>Provider reference · <code>{e(reference)}</code></p>'
                if pay.get("fallback_reason"):
                    payout += f'<p>{e(pay["fallback_reason"])}</p>'
            simulation = f'<aside class="simulation"><h2>Simulation summary</h2>{conversion}{payout}</aside>'

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SenFund receipt {e(inv)}</title>
<style>
:root {{ color: #221e18; background: #f5efe3; font: 15px/1.55 system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: clamp(12px, 5vw, 50px); }}
.receipt {{ max-width: 680px; margin: auto; padding: clamp(18px, 6vw, 44px); background: #fffcf6;
  border: 1px solid #dcd0b8; border-top: 5px solid #7a4e29; border-radius: 6px; }}
header {{ display: flex; align-items: start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
h1, h2, p, dl {{ margin: 0; }}
.brand {{ font-weight: 750; letter-spacing: -.025em; }}
h1 {{ margin-top: 8px; font: 700 clamp(28px, 6vw, 40px)/1.15 Georgia, serif; letter-spacing: -.035em; }}
h2 {{ font-size: 15px; }}
.badge {{ padding: 4px 10px; border-radius: 999px; background: #eee5d5; font-weight: 700; }}
.badge.paid {{ color: #244b39; background: #e4eee5; }}
.meta, .caption, dt {{ color: #665b4c; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 14px 0 24px; font-size: 13px; }}
.amount {{ display: grid; gap: 2px; padding: 16px 0; border-block: 1px dashed #cabca2; }}
.amount strong {{ font-size: clamp(24px, 6vw, 36px); line-height: 1.2; font-variant-numeric: tabular-nums; }}
.caption {{ font-size: 13px; }}
.section {{ margin-top: 23px; }}
.details {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; margin-top: 8px; }}
.details .wide {{ grid-column: 1 / -1; }}
dt {{ font-size: 12px; }}
dd {{ margin: 2px 0 0; overflow-wrap: anywhere; }}
code {{ font-size: .86em; }}
a {{ color: #664325; text-underline-offset: 2px; }}
.simulation {{ margin-top: 22px; padding: 12px 14px; background: #f5eddd; border-left: 2px solid #b28756; font-size: 13px; }}
.simulation p {{ margin-top: 4px; }}
footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid #ded3be; }}
@media (max-width: 460px) {{ .details {{ grid-template-columns: 1fr; }} }}
@media print {{
  @page {{ margin: 14mm; }}
  :root, .receipt {{ background: white; }}
  body, .receipt {{ padding: 0; }}
  .receipt {{ border: 0; }}
  .section, .simulation {{ break-inside: avoid; }}
}}
</style></head><body>
<main class="receipt">
  <header><div><p class="brand">SenFund</p><h1>Payment receipt</h1></div><span class="badge{' paid' if paid else ''}">{e(status)}</span></header>
  <p class="meta"><span>Invoice <code>{e(inv)}</code></span><span>Issued {e(issued)} UTC</span></p>
  <div class="amount"><span class="caption">{"Amount received" if paid else "Invoice amount"} · test {asset}</span>
    <strong>{e(amount)} {asset}</strong><span class="caption">{"Verified onchain" if paid else "Awaiting verified payment"}</span></div>
  <section class="section"><h2>Invoice details</h2><dl class="details">
    {field("Service", service)}
    {field("Billed to", customer) if customer else ""}
  </dl></section>
  {settlement}
  {simulation}
  <footer class="caption">Testnet receipt. Test tokens have no monetary value.</footer>
</main></body></html>"""
