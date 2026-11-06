"""Show that a payment made while the backend is down is recovered on restart.
Usage: stop the backend, then run scripts/recovery_demo.py <invoice id>.
It pays on-chain with scripts/pay.py, then runs the same reconcile step the server runs at startup."""
import socket, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT, load, setting, web3_for
from backend.service import SenFund

invoice = sys.argv[1]
port = int(setting("SENFUND_PORT", "8700"))
with socket.socket() as s:
    if s.connect_ex(("127.0.0.1", port)) == 0:
        raise SystemExit(f"backend is still running on {port}; stop it first")

cfg = load()
app = SenFund(cfg, w3=web3_for(cfg))
print("before:", app.get(invoice)["payment"])
subprocess.run([sys.executable, str(ROOT / "scripts" / "pay.py"), invoice], check=True)
print("paid while backend down; still:", app.get(invoice)["payment"])
app.reconcile(prioritize_recent=True)  # what verifier_loop does after restart
after = app.get(invoice)["payment"]
print("after reconcile:", after)
if after != "PAID":
    raise SystemExit("recovery did not mark the invoice paid")
