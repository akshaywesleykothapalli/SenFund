"""Run the full SenFund CRE-to-CCIP payout demo against an isolated fixture."""
import argparse
import json
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import cre_payout
from backend.ccip_local import LocalPayoutRelay
from backend.config import ROOT, load
from backend.server import make_handler
from backend.service import SenFund

INVOICE = "inv_4fe69ac0f479"
FIXTURE = ROOT / "docs/evidence/ccip-demo-fixture.sql"
STEPS = {
    "success": (("success", "USE_MUDREX", "COMPLETED", 1),),
    "mudrex_unavailable": (("mudrex_unavailable", "USE_P2P", "ON_HOLD", 2),),
    "timeout_recovery": (("timeout", "USE_MUDREX", "ON_HOLD", 1),
                         ("mudrex_unavailable", "HOLD", "ON_HOLD", 1)),
}


def run_demo(case, output, scratch):
    cfg = load()
    if cfg.env != "testnet" or not (cfg.ens_name and cfg.ens_resolver and cfg.ens_rpc):
        raise SystemExit("Set SENFUND_ENV=testnet and the three SENFUND_ENS_* variables in .env.")
    app = SenFund(cfg.with_(db_path=str(scratch / "demo.sqlite3"), cre_payouts=True, merchant_key=""))
    app.db.conn.executescript(FIXTURE.read_text())
    relay = LocalPayoutRelay()
    config = scratch / "cre-config.json"
    digest = app.get(INVOICE)["request"]["digest"]

    def capture(payload, rpc):
        return cre_payout.simulate(payload, rpc, config=config, audit_dir=output / payload["scenario"])

    payout_runner = partial(cre_payout.run, simulator=capture, authorize=relay.authorize)
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, payout_runner=payout_runner, local_ccip=True)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        config.write_text(json.dumps({"evidenceOrigin": origin}))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for scenario, route, payout, destination_route in STEPS[case]:
                step = output / scenario
                step.mkdir()
                request = Request(f"{origin}/api/invoices/{INVOICE}/payout", method="POST",
                                  data=json.dumps({"scenario": scenario}).encode(),
                                  headers={"Content-Type": "application/json"})
                print(f"Running CRE and checking the local destination contract for {scenario}…", flush=True)
                with urlopen(request, timeout=240) as response:
                    result = json.load(response)
                audit = next(op for op in result["operations"] if op["stage"] == "cre")
                detail = json.loads(audit["detail"])
                approval = relay.receiver.functions.approvals(bytes.fromhex(digest[2:])).call()
                orders = app.db.q("select order_id, status from mock_provider_orders")
                proof = {
                    "capturedAtUtc": datetime.now(timezone.utc).isoformat(),
                    "invoice": INVOICE, "invoiceDigest": digest, "scenario": scenario,
                    "route": audit["status"], "decision": detail, "payout": result["payout"],
                    "destinationRoute": approval[3], "simulatedOrders": orders,
                }
                (step / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
                expected_orders = 0 if case == "timeout_recovery" else 1
                observed = (audit["status"], result["payout"], approval[3], len(orders))
                if detail["source"] != "Chainlink CRE CLI" or observed != (route, payout, destination_route, expected_orders):
                    raise SystemExit(f"Unexpected result. Inspect {step / 'proof.json'} and the CLI logs.")
                if route != "HOLD":
                    ccip = detail.get("ccip", {})
                    if (ccip.get("beforeRoute"), ccip.get("afterRoute"), ccip.get("approvedRun")) != (
                            0, destination_route, detail["run"]):
                        raise SystemExit("CCIP evidence did not prove a fresh state change for this run.")
                    print(f"CCIP message {ccip['messageId']} changed receiver route 0 → {destination_route}.", flush=True)
                else:
                    if "ccip" in detail or detail["reason"] != "Prior payout outcome unknown":
                        raise SystemExit("Expected CRE to block the unresolved attempt before CCIP.")
                    print("CRE held the unresolved attempt. No new CCIP message or simulated order.", flush=True)
                print(f"{route} → payout {payout}. Evidence: {step / 'proof.json'}", flush=True)
        finally:
            server.shutdown()
            thread.join()
            app.db.conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=STEPS, default="success")
    parser.add_argument("--output", type=Path, help="New directory for proof and raw CLI logs")
    args = parser.parse_args()
    output = args.output or ROOT / ".data" / f"ccip-{args.case}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    output = output.resolve()
    output.mkdir(parents=True)
    with TemporaryDirectory(prefix="senfund-ccip-") as temp:
        run_demo(args.case, output, Path(temp))


if __name__ == "__main__":
    main()
