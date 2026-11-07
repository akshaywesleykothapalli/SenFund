# Railway: one container runs the Python settlement service (loopback :8700),
# the static checkout (loopback :8702) and the public Next.js app ($PORT).
FROM node:24-trixie
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt package.json package-lock.json ./
COPY contracts/package.json contracts/package-lock.json contracts/
RUN python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt \
 && npm ci && (cd contracts && npm ci)
COPY . .
RUN .venv/bin/python scripts/compile.py && npm run build
CMD ["sh", "scripts/railway_start.sh"]
