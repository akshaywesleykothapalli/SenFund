import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
create table if not exists invoices(
  id text primary key, invoice_id text unique not null, created_at int not null,
  usd text not null, amount_units text not null, data text not null, request text not null,
  payment text not null default 'OPEN', conversion text not null default 'NOT_STARTED',
  payout text not null default 'NOT_STARTED', needs_review int not null default 0,
  tx_hash text, last_reason text, corridor text not null default 'IN');
create table if not exists accounts(
  id text primary key, issuer text not null, subject text not null, email text not null,
  display_name text, unique(issuer,subject));
create table if not exists account_sessions(
  token_hash text primary key, account_id text not null, expires_at int not null, authenticated_at int not null);
create index if not exists account_sessions_owner on account_sessions(account_id);
create table if not exists wallet_challenges(
  id text primary key, account_id text not null, session_hash text not null, address text not null,
  purpose text not null, chain_id int not null, message text not null, expires_at int not null);
create index if not exists wallet_challenges_account on wallet_challenges(account_id);
create table if not exists verified_wallets(
  account_id text not null, address text not null, chain_id int not null, purpose text not null,
  verified_at int not null, primary key(chain_id,address,purpose));
create table if not exists invoice_owners(
  invoice text primary key, account_id text not null);
create index if not exists invoice_owners_account on invoice_owners(account_id,invoice);
create table if not exists invoice_creation_keys(
  scope text not null, key text not null, fingerprint text not null, invoice text not null,
  primary key(scope, key));
create table if not exists receipts(
  id integer primary key, invoice text not null, chain_id int not null, tx_hash text not null,
  log_index int not null, block_number int not null, block_hash text not null, payer text not null,
  amount text not null, status text not null default 'active', unique(chain_id, tx_hash, log_index));
create table if not exists transitions(
  id integer primary key, invoice text, stage text, old text, new text, source text, reason text, at int);
create table if not exists operations(
  key text primary key, invoice text, stage text, status text, external_id text, detail text, at int);
create table if not exists reconciliation_cursor(
  chain_id int not null, settlement text not null, block_number int not null, block_hash text not null,
  primary key(chain_id, settlement));
create table if not exists adapter_events(event_id text primary key, invoice text, payload text, outcome text, at int);
create table if not exists mock_provider_orders(key text primary key, order_id text unique, status text, detail text);
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if "corridor" not in {c[1] for c in self.conn.execute("pragma table_info(invoices)")}:
            self.conn.execute("alter table invoices add column corridor text not null default 'IN'")
        self.lock = threading.RLock()

    def q(self, sql, *args):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, *args):
        rows = self.q(sql, *args)
        return rows[0] if rows else None

    def x(self, sql, *args):
        with self.lock:
            return self.conn.execute(sql, args)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.conn.execute("begin immediate")
            try:
                yield
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

    def close(self):
        self.conn.close()
