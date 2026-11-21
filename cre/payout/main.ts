import {
  bytesToHex, consensusIdenticalAggregation, decodeJson, encodeCallMsg, EVMClient,
  handler, HTTPClient, HTTPCapability, LAST_FINALIZED_BLOCK_NUMBER, Runner,
  type HTTPPayload, type HTTPSendRequester, type Runtime,
} from "@chainlink/cre-sdk";
import {decodeFunctionResult, encodeFunctionData, parseAbi, toHex, zeroAddress, zeroHash, type Address} from "viem";

type Config = {evidenceOrigin: string; evidenceKey?: string};
type Receipt = {
  invoice: string; digest: string; recipient: string; environment: string; chainId: number;
  txHash: string; blockHash: string; logIndex: number; attemptKey: string;
};
type Provider = {
  attemptKey: string; available: boolean; attempt: string; route: string; status: string; simulated: boolean; corridor?: string; cashOut?: boolean;
};
type Input = {
  run: string; receipt: Receipt; provider?: Provider; scenario: string; name: string; resolver: Address;
  ensNetwork?: keyof typeof ensNetworks;
};
type Checks = {receipt: boolean; finalizedEns: boolean; provider: boolean; providerSnapshot: boolean};
type Decision = {
  run: string; receipt: Receipt; route: "HOLD" | "USE_MUDREX" | "USE_P2P"; reason: string;
  policy: "senfund-payout-v2"; checks: Checks; ensChainId: number;
};

const scenarios = new Set(["success", "hold", "fail", "timeout", "timeout_created", "mudrex_unavailable"]);
const addressPattern = /^0x[a-fA-F0-9]{40}$/;
const hashPattern = /^0x[a-fA-F0-9]{64}$/;

const ensNetworks = {
  sepolia: {chainId: 11155111, selector: 16015286601757825753n, resolver: "0x24e1d8e068620b647ca097f961a61055f4f42d72"},
  mainnet: {chainId: 1, selector: 5009297550715157269n, resolver: "0x06fdd07f007adac667177b46ab2eb9a75132cfd5"},
} as const;
const universalABI = parseAbi(["function resolve(bytes name, bytes data) view returns (bytes, address)"]);
const resolverABI = parseAbi([
  "function hasAddr(bytes32 node, uint256 coinType) view returns (bool)",
  "function addr(bytes32 node, uint256 coinType) view returns (bytes)",
]);
const coinType = 0x80000752n;

function sameReceipt(actual: Receipt, expected: Receipt): boolean {
  return actual.invoice === expected.invoice && actual.digest === expected.digest &&
    actual.recipient === expected.recipient && actual.environment === expected.environment &&
    actual.chainId === expected.chainId && actual.txHash === expected.txHash &&
    actual.blockHash === expected.blockHash && actual.logIndex === expected.logIndex &&
    actual.attemptKey === expected.attemptKey;
}

function sameProvider(actual: Provider, expected: Provider): boolean {
  return actual.attemptKey === expected.attemptKey && actual.available === expected.available &&
    actual.attempt === expected.attempt && actual.route === expected.route &&
    actual.status === expected.status && actual.simulated === expected.simulated &&
    (expected.corridor === undefined || actual.corridor === expected.corridor) &&
    (expected.cashOut === undefined || actual.cashOut === expected.cashOut);
}

function fetchEvidence<T>(runtime: Runtime<Config>, path: string): T {
  function fetchBody(requester: HTTPSendRequester, request: {url: string; key: string}): string {
    const headers: Record<string, string> = request.key ? {"X-SenFund-Evidence": request.key} : {};
    const response = requester.sendRequest({url: request.url, method: "GET", headers}).result();
    if (response.statusCode !== 200) throw new Error("Evidence endpoint rejected the request");
    return new TextDecoder().decode(response.body);
  }
  const response = new HTTPClient()
    .sendRequest(runtime, fetchBody, consensusIdenticalAggregation<string>())({
      url: runtime.config.evidenceOrigin + path, key: runtime.config.evidenceKey ?? "",
    })
    .result();
  return JSON.parse(response) as T;
}

function checkRecipient(runtime: Runtime<Config>, input: Input, deployment: typeof ensNetworks[keyof typeof ensNetworks]): boolean {
  const labels = input.name.split(".");
  if (labels.length < 2 || labels.at(-1) !== "eth" ||
      labels.some(label => !/^[a-z0-9-]{1,63}$/.test(label))) return false;
  const name = toHex(Uint8Array.from(labels.flatMap(label => [
    label.length, ...Array.from(label, letter => letter.charCodeAt(0)),
  ]).concat(0)));
  const evm = new EVMClient(deployment.selector);

  function read(functionName: "hasAddr" | "addr") {
    const profile = encodeFunctionData({abi: resolverABI, functionName, args: [zeroHash, coinType]});
    const data = encodeFunctionData({abi: universalABI, functionName: "resolve", args: [name, profile]});
    const response = evm.callContract(runtime, {
      call: encodeCallMsg({from: zeroAddress, to: deployment.resolver, data}),
      blockNumber: LAST_FINALIZED_BLOCK_NUMBER,
    }).result();
    const [value, resolver] = decodeFunctionResult({
      abi: universalABI, functionName: "resolve", data: bytesToHex(response.data),
    });
    if (resolver.toLowerCase() !== input.resolver.toLowerCase()) throw new Error("Unexpected ENS resolver");
    return decodeFunctionResult({abi: resolverABI, functionName, data: value});
  }
  return read("hasAddr") === true && read("addr") === input.receipt.recipient;
}

function onHttpTrigger(runtime: Runtime<Config>, payload: HTTPPayload): Decision {
  const input = decodeJson(payload.input) as Input;
  const network = input?.ensNetwork ?? "sepolia";
  const deployment = network === "sepolia" || network === "mainnet" ? ensNetworks[network] : undefined;
  const checks: Checks = {receipt: false, finalizedEns: false, provider: false, providerSnapshot: false};
  const result = (route: Decision["route"], reason: string): Decision => ({
    run: input?.run, receipt: input?.receipt, route, reason, policy: "senfund-payout-v2", checks,
    ensChainId: deployment?.chainId ?? 0,
  });
  const expected = input?.receipt;
  const id = expected?.invoice;
  if (!deployment || !expected || !/^inv_[a-f0-9]{12}$/.test(id) || !/^[a-f0-9]{32}$/.test(input.run) ||
      expected.environment !== "testnet" || expected.chainId !== 1874 ||
      !hashPattern.test(expected.digest) || !hashPattern.test(expected.txHash) || !hashPattern.test(expected.blockHash) ||
      !addressPattern.test(expected.recipient) || !addressPattern.test(input.resolver) ||
      typeof input.name !== "string" || !scenarios.has(input.scenario) ||
      !Number.isInteger(expected.logIndex) || expected.logIndex < 0 || expected.logIndex > 0xffffffff ||
      expected.attemptKey !== id + ":payout:testnet") {
    return result("HOLD", "Requires a valid Whitechain Sepolia receipt and payout challenge");
  }
  try {
    const receipt = fetchEvidence<Receipt>(runtime, "/api/cre/receipt/" + id);
    if (!sameReceipt(receipt, expected)) return result("HOLD", "Settlement evidence changed");
    checks.receipt = true;
    try {
      if (!checkRecipient(runtime, input, deployment)) return result("HOLD", "ENSv2 recipient mismatch or missing record");
    } catch {
      return result("HOLD", "Finalized ENSv2 lookup failed. If the name or record changed recently, wait for Ethereum finality and retry.");
    }
    checks.finalizedEns = true;
    const provider = fetchEvidence<Provider>(runtime, "/api/cre/provider/" + id + "?scenario=" + input.scenario);
    if (provider.simulated !== true || provider.attemptKey !== receipt.attemptKey ||
        typeof provider.available !== "boolean" || typeof provider.route !== "string" ||
        typeof provider.status !== "string" || !["none", "known", "unknown"].includes(provider.attempt)) {
      return result("HOLD", "Provider response does not match the attempt");
    }
    checks.provider = true;
    if (input.provider !== undefined) {
      if (!sameProvider(provider, input.provider)) return result("HOLD", "Provider snapshot changed before routing");
      checks.providerSnapshot = true;
    }
    if (provider.attempt === "known") {
      if (provider.route === "p2p") return result("USE_P2P", "Reconcile the existing simulated P2P order");
      if (provider.route === "mudrex" || provider.route === "eu_offramp" || provider.route === "legacy") {
        return result("USE_MUDREX", "Reconcile the existing simulated Mudrex order");
      }
    }
    if (provider.attempt !== "none" || provider.route !== "" || provider.status !== "") {
      return result("HOLD", "Prior payout outcome unknown");
    }
    if (provider.available) return result("USE_MUDREX", "Primary is available before dispatch");
    return result("USE_P2P", "Primary provider unavailable before dispatch. Use simulated P2P fallback.");
  } catch {
    return result("HOLD", "Settlement or provider evidence unavailable");
  }
}

export async function main() {
  const runner = await Runner.newRunner<Config>();
  await runner.run(() => [handler(new HTTPCapability().trigger({}), onHttpTrigger)]);
}
