#!/bin/sh
# Serves checkout (8702) and merchant site (8701) on their own, independent of the main app.
cd "$(dirname "$0")/.."
.venv/bin/python scripts/checkout_config.py || exit 1
.venv/bin/python -m http.server 8702 -b 127.0.0.1 -d checkout &
.venv/bin/python -m http.server 8701 -b 127.0.0.1 -d merchant-site
