"""Local Chainlink CRE simulation runner and fail-closed payout handoff."""
import json
import os
import re
import subprocess
import time
from uuid import uuid4

from . import chain, ens
from .config import ROOT, setting
from .state import InvalidTransition

SCENARIOS = {"success", "hold", "fail", "timeout", "timeout_created", "mudrex_unavailable"}
WORKFLOW_DIR = ROOT / "cre"
SIMULATED_RESULT = "Workflow Simulation Result:"
POLICY = "senfund-payout-v2"
REQUIRED_CHECKS = {"receipt", "finalizedEns", "provider", "providerSnapshot"}


def receipt_evidence(app, invoice):
    r = app.get(invoice)
    receipt = r["receipt"]
    if r["payment"] != "PAID" or r["conversion"] != "COMPLETED" or r["needs_review"] or not receipt:
        raise InvalidTransition("CRE requires a confirmed payment, completed demo conversion and no pending review")
    confirmed = chain.verify_receipt(app.w3, app.cfg, r["request"], receipt["tx_hash"])
    if (confirmed["block_hash"], confirmed["log_index"]) != (receipt["block_hash"], receipt["log_index"]):
        raise InvalidTransition("settlement changed during CRE verification")
    return {
        "invoice": invoice, "digest": r["request"]["digest"], "recipient": r["request"]["recipient"].lower(),
        "environment": app.cfg.env, "chainId": app.cfg.chain_id, "txHash": receipt["tx_hash"],
        "blockHash": receipt["block_hash"], "logIndex": receipt["log_index"],
        "attemptKey": f"{invoice}:payout:{app.cfg.env}",
    }


def provider_evidence(app, invoice, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown simulated payout scenario")
    r = app.get(invoice)
    key = f"{invoice}:payout:{app.cfg.env}"
    op = app.db.one("select status, detail from operations where key=?", key)
    order = app.db.one("select status from mock_provider_orders where key=?", key)
    return {
        "attemptKey": key,
        "available": scenario != "mudrex_unavailable",
        "attempt": "known" if order and op else "unknown" if order or op else "none",
        "route": json.loads(op["detail"]).get("route", "legacy") if op else "",
        "status": order["status"] if order else op["status"] if op else "",
        "simulated": True,
        "corridor": r["corridor"],
        "cashOut": bool(app.cash_out_intent(invoice)),
    }


def simulate(payload, ens_rpc, *, config=None, audit_dir=None):
    child_env = {key: os.environ[key] for key in ("PATH", "HOME", "USER", "TMPDIR", "XDG_CONFIG_HOME", "LANG")
                 if key in os.environ}
    child_env["SENFUND_ENS_RPC"] = ens_rpc
    cli = setting("SENFUND_CRE_CLI", "cre")
    target = ens.network(payload.get("ensNetwork", "sepolia")).cre_target
    command = [cli, "workflow", "simulate", "./payout", "--target", target, "--non-interactive",
               "--trigger-index", "0", "--http-payload", json.dumps(payload)]
    if config is not None:
        command.extend(["--config", str(config)])
    if audit_dir is not None:
        (audit_dir / "trigger.json").write_text(json.dumps(payload, indent=2) + "\n")
    try:
        result = subprocess.run(command, cwd=WORKFLOW_DIR, env=child_env, capture_output=True, text=True, timeout=120)
        if audit_dir is not None:
            for filename, raw in (("cli.stdout", result.stdout), ("cli.stderr", result.stderr)):
                (audit_dir / filename).write_text(raw.replace(ens_rpc, "<ENS_RPC>") if ens_rpc else raw)
            (audit_dir / "cli.exit").write_text(f"{result.returncode}\n")
        result.check_returncode()
        # Read the result section only. Never accept a decision from debug logs.
        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        tail = output.split(SIMULATED_RESULT, 1)[1].lstrip()
        decision, _ = json.JSONDecoder().raw_decode(tail)
        if not isinstance(decision, dict):
            raise ValueError("expected a CRE result object")
        return decision
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        raise RuntimeError("CRE simulation did not return a decision. Check the CLI login and setup.") from None


def _record(app, invoice, nonce, route, reason, source, **evidence):
    app.db.x(
        "insert into operations(key,invoice,stage,status,detail,at) values(?,?,?,?,?,?) "
        "on conflict(key) do update set status=excluded.status,detail=excluded.detail,at=excluded.at",
        f"{invoice}:cre:{app.cfg.env}", invoice, "cre", route,
        json.dumps({"run": nonce, "reason": reason, "source": source, "simulated": True, **evidence}), int(time.time()),
    )


def run(app, lock, invoice, scenario, *, simulator=None, authorize=None):
    if not app.cfg.ens_name or not app.cfg.ens_resolver or not app.cfg.ens_rpc:
        raise InvalidTransition("configure the enrolled ENSv2 name and resolver before running CRE")
    deployment = ens.network(app.cfg.ens_network)
    nonce = uuid4().hex
    with lock:
        app.check_cash_out_route(invoice, scenario)
        receipt = receipt_evidence(app, invoice)
        provider = provider_evidence(app, invoice, scenario)
    payload = {"run": nonce, "receipt": receipt, "scenario": scenario,
               "name": app.cfg.ens_name, "resolver": app.cfg.ens_resolver, "provider": provider,
               "ensNetwork": app.cfg.ens_network}
    failure = None
    try:
        output = (simulator or simulate)(payload, app.cfg.ens_rpc)
    except RuntimeError as error:
        failure = str(error)

    with lock:
        if provider["cashOut"] and provider["attempt"] == "none" and app.get(invoice)["payout"] != "NOT_STARTED":
            return app.get(invoice)
        if failure is not None:
            _record(app, invoice, nonce, "HOLD", failure, "local runner")
            return app.get(invoice)
        if (output.get("run") != nonce or output.get("receipt") != receipt
                or output.get("ensChainId") != deployment.chain_id):
            raise InvalidTransition("CRE decision does not match this run, receipt and ENS network")
        route, reason = output.get("route"), output.get("reason")
        if route not in ("USE_MUDREX", "USE_P2P", "HOLD") or not isinstance(reason, str) or len(reason) > 200:
            raise InvalidTransition("CRE returned an invalid decision")
        checks = output.get("checks")
        if route != "HOLD" and (output.get("policy") != POLICY or not isinstance(checks, dict)
                                or any(checks.get(check) is not True for check in REQUIRED_CHECKS)):
            raise InvalidTransition("CRE did not pass all payout evidence checks")
        known = provider["attempt"] == "known"
        fresh = provider["attempt"] == "none"
        if route == "USE_P2P" and not ((fresh and not provider["available"]) or (known and provider["route"] == "p2p")):
            raise InvalidTransition("CRE cannot move an existing attempt to P2P")
        if route == "USE_MUDREX" and not ((fresh and provider["available"]) or (known and provider["route"] in ("mudrex", "eu_offramp", "legacy"))):
            raise InvalidTransition("CRE cannot create or move an uncertain Mudrex attempt")
        if route != "HOLD":
            # CRE reads finalized ENS records. Check the latest address again immediately before dispatch.
            try:
                recipient = ens.resolve_recipient(app.cfg).lower()
            except Exception:
                recipient = None
            if recipient != receipt["recipient"]:
                _record(app, invoice, nonce, "HOLD", "Latest ENSv2 recipient could not be confirmed", "local runner")
                return app.get(invoice)

        try:
            unchanged = receipt_evidence(app, invoice) == receipt and provider_evidence(app, invoice, scenario) == provider
        except (chain.VerificationError, InvalidTransition):
            unchanged = False
        if not unchanged:
            _record(app, invoice, nonce, "HOLD", "Settlement or prior attempt changed during CRE run", "local runner")
            return app.get(invoice)

        evidence = {"policy": output.get("policy"), "checks": checks}
        if isinstance(checks, dict) and checks.get("finalizedEns") is True:
            evidence["ens"] = {"name": payload["name"], "resolver": payload["resolver"],
                               "recipient": receipt["recipient"], "chainId": deployment.chain_id,
                               "network": deployment.label}
        if route != "HOLD" and authorize is not None:
            try:
                evidence["ccip"] = authorize(receipt, nonce, route)
            except InvalidTransition as error:
                _record(app, invoice, nonce, "HOLD", str(error), "local CCIP gate", **evidence)
                return app.get(invoice)
        _record(app, invoice, nonce, route, reason, "Chainlink CRE CLI", **evidence)
        if route == "HOLD":
            return app.get(invoice)
        return app.run_payout(invoice, "mudrex_unavailable" if route == "USE_P2P" else scenario)
