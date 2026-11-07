"""Verified identities and revocable sessions for the private merchant API."""

import hashlib
import hmac
import secrets
import time
from uuid import uuid4

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from backend.adapters import CORRIDORS


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Accounts:
    def __init__(self, db, issuer, bridge_secret, operator_subject=""):
        if not issuer.startswith("https://") or len(bridge_secret) < 32:
            raise ValueError("Account mode requires an HTTPS issuer and a strong API bridge secret.")
        self.db = db
        self.issuer = issuer
        self.bridge_secret = bridge_secret.encode()
        self.operator_subject = operator_subject

    def trusted_bridge(self, supplied):
        return bool(supplied) and hmac.compare_digest(supplied.encode(), self.bridge_secret)

    def sign_in(self, claims):
        subject, email = claims.get("sub"), claims.get("email")
        now, authenticated_at = int(time.time()), claims.get("auth_time")
        if (claims.get("iss") != self.issuer or claims.get("email_verified") is not True
                or not isinstance(subject, str) or not 0 < len(subject) <= 255
                or not isinstance(email, str) or not 0 < len(email) <= 254
                or type(authenticated_at) is not int or not now - 330 <= authenticated_at <= now + 30):
            raise ValueError("A verified account from the configured identity provider is required.")
        token = secrets.token_urlsafe(32)
        with self.db.transaction():
            self.db.x(
                "insert into accounts(id,issuer,subject,email) values(?,?,?,?) "
                "on conflict(issuer,subject) do update set email=excluded.email",
                uuid4().hex, self.issuer, subject, email,
            )
            row = self.db.one("select id from accounts where issuer=? and subject=?", self.issuer, subject)
            self.db.x("delete from account_sessions where expires_at<=?", now)
            self.db.x("insert into account_sessions(token_hash,account_id,expires_at,authenticated_at) values(?,?,?,?)",
                      token_hash(token), row["id"], now + 8 * 3600, authenticated_at)
        return token

    def actor(self, token):
        if not token or len(token) > 128:
            return None
        return self.db.one(
            "select a.id,a.subject,a.email,a.display_name,s.authenticated_at from accounts a "
            "join account_sessions s on s.account_id=a.id where s.token_hash=? and s.expires_at>?",
            token_hash(token), int(time.time()),
        )

    def profile(self, actor):
        prefs = self.db.one("select role,corridor from account_prefs where account_id=?", actor["id"])
        return {"id": actor["id"], "email": actor["email"], "displayName": actor["display_name"],
                "canIssue": self.can_issue(actor), "role": prefs["role"] if prefs else None,
                "corridor": prefs["corridor"] if prefs else None}

    def update_prefs(self, actor, role, corridor):
        if role not in {"payee", "payer"} or corridor not in CORRIDORS:
            raise ValueError("Choose whether you get paid or pay, and a payout corridor.")
        self.db.x("insert into account_prefs(account_id,role,corridor) values(?,?,?) on conflict(account_id) "
                  "do update set role=excluded.role, corridor=excluded.corridor", actor["id"], role, corridor)
        return self.profile(actor)

    def update_profile(self, actor, display_name):
        if not isinstance(display_name, str) or not 0 < len(display_name.strip()) <= 100:
            raise ValueError("Enter a display name using up to 100 characters.")
        self.db.x("update accounts set display_name=? where id=?", display_name.strip(), actor["id"])
        return self.profile({**actor, "display_name": display_name.strip()})

    def can_issue(self, actor):
        return bool(self.operator_subject and actor["subject"] == self.operator_subject)

    def sign_out(self, token, actor, all_sessions=False):
        if all_sessions:
            self.db.x("delete from account_sessions where account_id=?", actor["id"])
        else:
            self.db.x("delete from account_sessions where token_hash=?", token_hash(token))

    def require_owner(self, invoice, account):
        if not self.db.one("select 1 from invoice_owners where invoice=? and account_id=?", invoice, account):
            raise KeyError(invoice)

    def wallets(self, actor):
        return self.db.q("select address,chain_id,purpose,verified_at from verified_wallets where account_id=? order by verified_at desc",
                         actor["id"])

    def wallet_challenge(self, actor, session, body, origin, chain_id):
        if int(time.time()) - actor["authenticated_at"] > 300:
            raise ValueError("Sign in again before verifying a wallet.")
        purpose, address = body.get("purpose"), body.get("address")
        if not isinstance(purpose, str) or purpose not in {"signer", "recipient"} or not isinstance(address, str) or not Web3.is_address(address):
            raise ValueError("Provide a valid wallet address and a supported purpose.")
        address = Web3.to_checksum_address(address)
        if int(address, 16) == 0:
            raise ValueError("The zero address cannot be linked.")
        now = int(time.time())
        challenge = secrets.token_hex(24)
        message = (
            f"SenFund wallet ownership proof\nOrigin: {origin}\nAccount: {actor['id']}\n"
            f"Address: {address}\nChain ID: {chain_id}\nPurpose: {purpose}\n"
            f"Nonce: {challenge}\nExpires at: {now + 300}\n"
            "This signature proves wallet control and does not authorize a payment."
        )
        with self.db.transaction():
            self.db.x("delete from wallet_challenges where expires_at<=?", now)
            self.db.x("delete from wallet_challenges where account_id=? and purpose=?", actor["id"], purpose)
            self.db.x("insert into wallet_challenges values(?,?,?,?,?,?,?,?)",
                      challenge, actor["id"], token_hash(session), address, purpose, chain_id, message, now + 300)
        return {"challenge": challenge, "message": message, "chainId": chain_id}

    def verify_wallet(self, actor, session, body):
        if int(time.time()) - actor["authenticated_at"] > 300:
            raise ValueError("Sign in again before verifying a wallet.")
        challenge, signature = body.get("challenge"), body.get("signature")
        if (not isinstance(challenge, str) or len(challenge) != 48 or not isinstance(signature, str)
                or len(signature) != 132 or not signature.startswith("0x")):
            raise ValueError("Invalid wallet proof.")
        now = int(time.time())
        with self.db.transaction():
            row = self.db.one(
                "select * from wallet_challenges where id=? and account_id=? and session_hash=? and expires_at>?",
                challenge, actor["id"], token_hash(session), now,
            )
            if row is None:
                raise ValueError("Wallet challenge is invalid, expired or already used.")
            try:
                address = Account.recover_message(encode_defunct(text=row["message"]), signature=signature)
            except Exception:
                raise ValueError("Invalid wallet proof.") from None
            if address != row["address"]:
                raise ValueError("The signature does not match the requested wallet.")
            existing = self.db.one("select account_id from verified_wallets where chain_id=? and address=? and purpose=?",
                                   row["chain_id"], address, row["purpose"])
            if existing and existing["account_id"] != actor["id"]:
                raise ValueError("This wallet is already associated with another account for this purpose.")
            self.db.x("delete from wallet_challenges where id=?", challenge)
            self.db.x(
                "insert into verified_wallets(account_id,address,chain_id,purpose,verified_at) values(?,?,?,?,?) "
                "on conflict(chain_id,address,purpose) do update set verified_at=excluded.verified_at",
                actor["id"], address, row["chain_id"], row["purpose"], now,
            )
        return self.wallets(actor)

    def assign_legacy_invoice(self, invoice, account):
        with self.db.transaction():
            if not self.db.one("select 1 from invoices where id=?", invoice):
                raise KeyError(invoice)
            if not self.db.one("select 1 from accounts where id=?", account):
                raise KeyError(account)
            self.db.x("insert into invoice_owners(invoice,account_id) values(?,?)", invoice, account)
