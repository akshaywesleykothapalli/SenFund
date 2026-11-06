"""Conversion and payout adapters. Everything here is SIMULATED; the live adapter refuses to run."""
import uuid
from decimal import Decimal

CONVERSION_FEE_USD = Decimal("0.50")
# Fixture corridors: rates and fees are not live quotes.
CORRIDORS = {
    "IN": {"currency": "INR", "rate": Decimal("80"), "fee": Decimal("40"), "primary": "mudrex", "fallback": "p2p",
           "note": "FIU-registered provider; 1% TDS applies"},
    "EU": {"currency": "EUR", "rate": Decimal("0.92"), "fee": Decimal("1.50"), "primary": "eu_offramp", "fallback": "p2p",
           "note": "MiCA-licensed off-ramp"},
}


class ProviderTimeout(Exception):
    """Request outcome unknown: the provider may or may not have created the order."""


class MockConversion:
    label = "Simulated USDT→USD conversion (fixture, no real exchange)"

    def convert(self, usdt_units: int, decimals: int) -> dict:
        usd = Decimal(usdt_units) / (Decimal(10) ** decimals)
        return {"simulated": True, "gross_usd": str(usd), "fee_usd": str(CONVERSION_FEE_USD), "net_usd": str(usd - CONVERSION_FEE_USD)}


class MockRemittance:
    """Local fixtures per corridor. P2P waits for a separate simulated credit event."""
    label = "Simulated payout (mock provider, no money moves)"

    def __init__(self, db, scenario="success", route="mudrex", corridor="IN"):
        self.db, self.scenario, self.route, self.c = db, scenario, route, CORRIDORS[corridor]

    def quote(self, net_usd: str) -> dict:
        c = self.c
        amount = Decimal(net_usd) * c["rate"] - c["fee"]
        return {"simulated": True, "route": self.route, "currency": c["currency"], "rate": str(c["rate"]),
                "fee": str(c["fee"]), "amount": str(amount.quantize(Decimal("0.01"))), "note": c["note"]}

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
            prefix = f"SIM-{self.route.upper()}-"
        oid = prefix + uuid.uuid4().hex[:10].upper()
        self.db.x("insert into mock_provider_orders(key,order_id,status,detail) values(?,?,?,?)", key, oid, status, quote["amount"])
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
