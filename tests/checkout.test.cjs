const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {test} = require("node:test");
const vm = require("node:vm");

const addr = n => "0x" + n.toString(16).padStart(40, "0");
const word = n => n.toString(16).padStart(64, "0");
const trust = {chainId: 1874, contract: addr(1), token: addr(2), merchant: addr(3), recipient: addr(4)};
const invoice = {...trust, invoiceId: "0x" + "ab".repeat(32), signature: "0x" + "ab".repeat(65),
  amount: "25000000", expiry: Math.floor(Date.now() / 1000) + 3600};
const ctx = vm.createContext({document: {getElementById: () => ({append() {}}), createElement: () => ({})}});
const source = readFileSync(require.resolve("../checkout/app.js"), "utf8");
vm.runInContext(source.slice(0, source.indexOf("init().catch")), ctx);

function wallet(valid = true, state = 0) {
  const calls = [];
  const provider = {request: async ({method}) => {
    calls.push(method);
    if (method === "eth_requestAccounts") return [addr(9)];
    if (method === "eth_chainId") return "0x752";
    if (method === "eth_call") return "0x" + word(42) + word(Number(valid)) + word(state);
    throw new Error("Unexpected wallet call: " + method);
  }};
  ctx.window = {ethereum: provider};
  return calls;
}

test("untrusted chain, token and spender are rejected before any wallet call", async () => {
  for (const change of [{chainId: 1}, {token: addr(99)}, {contract: addr(99)}]) {
    const calls = wallet();
    await assert.rejects(ctx.pay({...invoice, ...change}, trust), /trusted checkout/);
    assert.deepEqual(calls, []);
  }
});

test("invalid signature, closed invoice and changed recipient cannot request approval", async () => {
  for (const [valid, state, recipient] of [[false, 0, addr(4)], [true, 1, addr(4)], [true, 0, addr(99)]]) {
    const calls = wallet(valid, state);
    await assert.rejects(ctx.pay(invoice, {...trust, recipient}), /signature|address changed/);
    assert.ok(!calls.includes("eth_sendTransaction"));
  }
});
