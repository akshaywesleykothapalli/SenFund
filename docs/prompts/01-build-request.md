# Build prompt (local file path shortened)

Read `SenFund PRD.docx` as the project specification. Inspect the current SenFund folder, reuse existing code, make a short build plan, and start implementing in this session.

Build the core flow first. Create and sign a USD invoice, pay it with official test USDT on Whitechain Sepolia, and verify the onchain receipt. Then add the dashboard, clearly labeled simulated USD conversion and INR payout, and an independent checkout that works with the main app stopped. Keep mainnet and live payouts disabled. Follow the sponsor requirements for ENSv2, Whitechain and Chainlink CRE.

Run tests for tampered invoices, wrong network or token, duplicate settlement, uncertain payout retries, and recovery with the main app stopped. If public-testnet access is blocked, continue with local tests and identify which checks still require a real transaction.

Use SenFund branding throughout. Keep the UI, screenshots, and exports free of Claude and Ponytail watermarks. Keep `.claude/`, local agent settings, caches, and secrets out of version control. Use `.git/info/exclude` for machine-specific files if needed. Flag any of those files that are already tracked.

Leave staging, commits, and GitHub publishing for me. Preserve required license notices and keep a factual AI-use disclosure for the ETHGlobal submission, along with the PRD, prompts, and planning artifacts required by the event. Finish with run instructions, test results, and a short list of what still needs verification.
