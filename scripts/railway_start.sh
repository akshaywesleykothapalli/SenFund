#!/bin/sh
# Railway entrypoint. Env vars come from the Railway dashboard, never from a committed file.
set -e
cd "$(dirname "$0")/.."
.venv/bin/python scripts/checkout_config.py || echo "checkout trust.json not generated; checkout disabled"
.venv/bin/python -m http.server 8702 -b 127.0.0.1 -d checkout &
.venv/bin/python -m backend.server &
exec npx next start --hostname 0.0.0.0 --port "${PORT:-3000}"
