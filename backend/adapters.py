"""Conversion and payout adapters. Everything here is SIMULATED; the live adapter refuses to run."""
import uuid
from decimal import Decimal

FX_INR_PER_USD = Decimal("80")       # fixture rate
CONVERSION_FEE_USD = Decimal("0.50")
PAYOUT_FEE_INR = Decimal("40")


class ProviderTimeout(Exception):
    """Request outcome unknown: the provider may or may not have created the order."""


class MockConversion:
    label = "Simulated USDT→USD conversion (fixture, no real exchange)"

    def convert(self, usdt_units: int, decimals: int) -> dict:
        usd = Decimal(usdt_units) / (Decimal(10) ** decimals)
        return {"simulated": True, "gross_usd": str(usd), "fee_usd": str(CONVERSION_FEE_USD), "net_usd": str(usd - CONVERSION_FEE_USD)}


class MockRemittance:
    """Local fixtures for Mudrex and P2P. P2P waits for a separate simulated credit event."""
    label = "Simulated INR payout (mock provider, no money moves)"

    def __init__(self, db, scenario="success", route="mudrex"):
        self.db, self.scenario, self.route = db, scenario, route

    def quote(self, net_usd: str) -> dict:
        inr = Decimal(net_usd) * FX_INR_PER_USD - PAYOUT_FEE_INR
        return {"simulated": True, "route": self.route, "rate": str(FX_INR_PER_USD), "fee_inr": str(PAYOUT_FEE_INR), "inr": str(inr.quantize(Decimal("0.01")))}

    def create(self, key: str, quote: dict, recipient: dict) -> dict:
        if self.scenario == "timeout":
            raise ProviderTimeout("no response")
        existing = self.find_by_key(key)
        if existing:  # provider-side idempotency
            return existing
        if self.route == "p2p":
            status = "ON_HOLD"
            prefix = "SIM-P2P-"
        else:
            status = {"success": "COMPLETED", "hold": "ON_HOLD", "fail": "FAILED", "timeout_created": "COMPLETED"}[self.scenario]
            prefix = "SIM-MUDREX-"
        oid = prefix + uuid.uuid4().hex[:10].upper()
        self.db.x("insert into mock_provider_orders(key,order_id,status,detail) values(?,?,?,?)", key, oid, status, quote["inr"])
        if self.scenario == "timeout_created":
            raise ProviderTimeout("created, but response lost")
        return {"order_id": oid, "status": status}

    def find_by_key(self, key: str):
        r = self.db.one("select order_id,status from mock_provider_orders where key=?", key)
        return {"order_id": r["order_id"], "status": r["status"]} if r else None

    def simulate_bank_credit(self, key: str, order_id: str) -> bool:
        return self.db.x("update mock_provider_orders set status='COMPLETED' where key=? and order_id=? and status='ON_HOLD'",
                         key, order_id).rowcount == 1

    def status(self, order_id: str):
        r = self.db.one("select status from mock_provider_orders where order_id=?", order_id)
        return r["status"] if r else None


class LiveRemittance:
    def __init__(self, *a, **k):
        raise RuntimeError("Live payouts are disabled in this build (testnet only)")
