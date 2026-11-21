"""Email/password accounts for the loopback merchant workspace."""
import hashlib
import hmac
import re
import secrets
import time
from uuid import uuid4

from .accounts import Accounts


ADMIN = "admin@admin.com"


def password_hash(password, salt=None):
    salt = secrets.token_bytes(16) if salt is None else salt
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


class LocalAccounts(Accounts):
    def __init__(self, db, bridge_secret, admin_hash):
        super().__init__(db, "https://local.senfund.invalid", bridge_secret, ADMIN)
        if not re.fullmatch(r"[a-f0-9]{32}:[a-f0-9]{128}", admin_hash):
            raise ValueError("Configure the local admin password hash before starting SenFund.")
        self.admin_hash = admin_hash
        with db.transaction():
            self.add_account(ADMIN, admin_hash)

    def add_account(self, email, hashed):
        account_id = uuid4().hex
        row = self.db.x(
            "insert or ignore into accounts(id,issuer,subject,email) values(?,?,?,?)",
            account_id, self.issuer, email, email,
        )
        if row.rowcount != 1:
            return None
        self.db.x("insert into local_credentials(account_id,password_hash) values(?,?)", account_id, hashed)
        return account_id

    def sign_in(self, body):
        return self.authenticate(body, register=False)

    def authenticate(self, body, *, register):
        email, password = body.get("email"), body.get("password")
        email = email.strip().lower() if isinstance(email, str) else ""
        if (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
                or not isinstance(password, str) or not 8 <= len(password) <= 128):
            raise ValueError("Enter a valid email and a password of 8 to 128 characters.")
        if register:
            hashed = password_hash(password)
            with self.db.transaction():
                account_id = self.add_account(email, hashed)
                if not account_id:
                    raise ValueError("This email already has an account. Sign in instead.")
                return self.issue_session(account_id, int(time.time()))

        row = self.db.one(
            "select a.id,c.password_hash from accounts a join local_credentials c on c.account_id=a.id "
            "where a.issuer=? and a.subject=?",
            self.issuer, email,
        )
        stored = row["password_hash"] if row else self.admin_hash
        salt = bytes.fromhex(stored.split(":", 1)[0])
        if not hmac.compare_digest(password_hash(password, salt), stored) or row is None:
            raise ValueError("Email or password is incorrect.")
        with self.db.transaction():
            return self.issue_session(row["id"], int(time.time()))
