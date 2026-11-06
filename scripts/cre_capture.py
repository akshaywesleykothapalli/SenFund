"""Run the CRE payout workflow for one paid invoice and save the decision as evidence.
Usage: scripts/cre_capture.py <invoice id> [scenario]   (needs `cre login` and the ENSv2 settings in .env)
Writes docs/evidence/cre-<invoice>-<scenario>.json."""
import json, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import cre_payout
from backend.config import ROOT, load, web3_for
from backend.service import SenFund

invoice = sys.argv[1]
scenario = sys.argv[2] if len(sys.argv) > 2 else "success"
cfg = load()
app = SenFund(cfg, w3=web3_for(cfg))
result = cre_payout.run(app, threading.Lock(), invoice, scenario)
op = app.db.one("select status, detail from operations where key=?", f"{invoice}:cre:{cfg.env}")
if not op:
    raise SystemExit("CRE recorded no decision")
evidence = {"invoice": invoice, "scenario": scenario, "env": cfg.env, "capturedAt": int(time.time()),
            "route": op["status"], "decision": json.loads(op["detail"]),
            "payout": result.get("payout"), "receipt": result.get("receipt")}
out = ROOT / "docs" / "evidence" / f"cre-{invoice}-{scenario}.json"
out.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
print(f"{evidence['route']} via {evidence['decision'].get('source')}: {out.relative_to(ROOT)}")
