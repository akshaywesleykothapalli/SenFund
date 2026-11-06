"""SenFund core: invoices, receipt verification, reorg recheck, reconciliation, simulated conversion/payout."""
import hashlib
import html
import json
import os
import re
import time
import uuid
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
        "fallback": f"Your payout of {amt} is going via protected P2P. Your USDT stays locked until your bank confirms the credit.",
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
                       corridor: str = "IN") -> dict:
        if corridor not in CORRIDORS:
            raise ValueError("Unknown payout corridor.")
        if not (self.cfg.settlement and self.merchant):
            raise ValueError("deployment not configured: need settlement contract and merchant key")
        try:
            usd_d = Decimal(str(usd))
        except InvalidOperation:
            raise ValueError("Enter a valid USD amount.") from None
        if (not usd_d.is_finite() or usd_d <= 0 or usd_d.adjusted() >= 22
                or usd_d.as_tuple().exponent < -min(2, self.cfg.token_decimals)):
            raise ValueError("Enter a positive USD amount with up to two decimal places and 22 whole digits.")
        numerator, denominator = usd_d.as_integer_ratio()
        units = numerator * 10 ** self.cfg.token_decimals // denominator
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
            [units, description, customer, data["beneficiary"], ttl], sort_keys=True
        ).encode()).hexdigest()
        if idempotency_key is not None:
            existing = self._invoice_for_key(scope, idempotency_key, fingerprint)
            if existing is not None:
                return existing

        recipient = ens.resolve_recipient(self.cfg) if self.cfg.env == "testnet" else self.cfg.recipient
        if not recipient:
            raise ValueError("recipient not configured")
        inv = "inv_" + uuid.uuid4().hex[:12]
        now = int(time.time())
        req = chain.sign_request({
            "chainId": self.cfg.chain_id, "contract": Web3.to_checksum_address(self.cfg.settlement),
            "invoiceId": "0x" + os.urandom(32).hex(), "merchant": self.merchant,
            "domainName": self.cfg.domain_name, "recipient": Web3.to_checksum_address(recipient),
            "token": Web3.to_checksum_address(self.cfg.token), "amount": str(units),
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
        return {**r["request"], "usd": r["usd"],
                "tokenSymbol": "USDT (test)", "tokenDecimals": self.cfg.token_decimals}

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
    def run_payout(self, inv: str, scenario: str = "success") -> dict:
        r = self.get(inv)
        if r["payment"] != "PAID" or r["conversion"] != "COMPLETED" or r["needs_review"]:
            raise InvalidTransition("payout requires verified payment, completed conversion and no pending review")
        if scenario not in ("success", "hold", "fail", "timeout", "timeout_created", "mudrex_unavailable"):
            raise ValueError("unknown simulated payout scenario")
        if r["payout"] in ("COMPLETED", "FAILED"):
            return r
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
        return {"invoice": inv, "usd": r["usd"], "description": r["data"].get("description", ""),
                "environment": self.cfg.env, "chainId": self.cfg.chain_id, "testnetOnly": True,
                "settlement": {k: rc[k] for k in ("tx_hash", "block_number", "block_hash", "log_index", "payer", "amount")},
                "states": {"payment": r["payment"], "conversion": r["conversion"], "payout": r["payout"]},
                "operations": ops, "history": r["history"],
                "note": "Conversion and payout are simulated. No money moved."}

    def receipt_html(self, inv: str) -> str:
        r = self.get(inv)
        e = html.escape
        rc = r["receipt"]
        ops = {o["stage"]: o for o in r["operations"]}
        conv = json.loads(ops["conversion"]["detail"]) if "conversion" in ops else None
        pay = json.loads(ops["payout"]["detail"]) if "payout" in ops else None
        explorer = f'{self.cfg.explorer}/tx/{rc["tx_hash"]}' if rc else ""
        onchain = (f"<p><b>Verified onchain.</b> Tx <a href='{e(explorer)}'>{e(rc['tx_hash'])}</a>, block {rc['block_number']}, "
                   f"payer {e(rc['payer'])}, {Decimal(rc['amount']) / 10 ** self.cfg.token_decimals} test USDT on chain {self.cfg.chain_id}.</p>"
                   if rc else f"<p>Not verified. Payment state: {e(r['payment'])}.</p>")
        conv_s = (f"<p>SIMULATED. {e(conv['gross_usd'])} USD gross, {e(conv['fee_usd'])} fee, {e(conv['net_usd'])} USD net. No exchange was used.</p>"
                  if conv else "<p>Not run.</p>")
        payout_label = {"COMPLETED": "Simulated payout completed", "ON_HOLD": "Simulated payout on hold",
                        "FAILED": "Simulated payout failed"}.get(r["payout"], f"Simulated payout: {r['payout']}")
        route_labels = {"mudrex": "Mudrex", "p2p": "Protected P2P fallback", "eu_offramp": "MiCA off-ramp"}
        route = route_labels.get(pay.get("route"), "Mock remittance") if pay else ""
        fallback_reason = pay.get("fallback_reason", "") if pay else ""
        pay_s = (f"<p>{e(payout_label)}. Route: {e(route)} (simulated). {e(fallback_reason)}"
                 f"</p><p>{e(pay['amount'])} {e(pay['currency'])} at fixture rate {e(pay['rate'])}, fee {e(pay['fee'])} {e(pay['currency'])}. "
                 f"Mock provider ref {e(ops['payout']['external_id'] or 'none')}. No money moved.</p>" if pay else "<p>Not run.</p>")
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>SenFund receipt {e(inv)}</title>
<style>body{{font:15px system-ui;max-width:720px;margin:2em auto;color:#14213d}}h1{{color:#0b6e4f}}section{{border:1px solid #ccd;border-radius:8px;padding:0 1em;margin:1em 0}}.sim{{background:#fff7e0}}</style></head>
<body><h1>SenFund receipt</h1><p>Invoice {e(inv)} · {e(r['data']['description'])} · {e(r['usd'])} USD (test pricing) · Testnet only</p>
<section><h2>1. Onchain settlement (Whitechain Sepolia)</h2>{onchain}</section>
<section class="sim"><h2>2. USD conversion (simulated)</h2>{conv_s}</section>
<section class="sim"><h2>3. Payout (simulated)</h2>{pay_s}</section>
<p><small>Sections 2 and 3 are simulations for demonstration. Bank details are excluded.</small></p></body></html>"""
