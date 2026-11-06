"""Validated state machine. Each stage moves only along these edges; anything else (e.g. a stale
callback trying to move a COMPLETED payout back to SUBMITTED) raises InvalidTransition."""
import time

ALLOWED = {
    "payment": {
        "OPEN": {"SUBMITTED", "PAID", "CANCELLED"},
        "SUBMITTED": {"PAID", "OPEN"},
        "PAID": {"OPEN"},  # only on detected reorg
    },
    "conversion": {
        "NOT_STARTED": {"PENDING"},
        "PENDING": {"COMPLETED", "FAILED"},
        "FAILED": {"PENDING"},
    },
    "payout": {
        "NOT_STARTED": {"QUOTED"},
        "QUOTED": {"SUBMITTED", "ON_HOLD", "COMPLETED", "FAILED"},
        "SUBMITTED": {"COMPLETED", "FAILED", "ON_HOLD"},
        "ON_HOLD": {"SUBMITTED", "COMPLETED", "FAILED"},
        "FAILED": {"QUOTED"},
    },
}


class InvalidTransition(Exception):
    pass


def transition(db, invoice: str, stage: str, new: str, source: str, reason: str = "") -> bool:
    cur = db.one(f"select {stage} from invoices where id=?", invoice)[stage]
    if cur == new:
        return False
    if new not in ALLOWED[stage].get(cur, set()):
        raise InvalidTransition(f"{stage}: {cur} -> {new} not allowed")
    cur_after = db.x(f"update invoices set {stage}=? where id=? and {stage}=?", new, invoice, cur)
    if cur_after.rowcount != 1:  # lost a race; caller re-reads
        raise InvalidTransition(f"{stage}: concurrent change from {cur}")
    db.x("insert into transitions(invoice,stage,old,new,source,reason,at) values(?,?,?,?,?,?,?)",
         invoice, stage, cur, new, source, reason, int(time.time()))
    return True
