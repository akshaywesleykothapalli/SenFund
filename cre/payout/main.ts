import {
  bytesToHex, consensusIdenticalAggregation, decodeJson, encodeCallMsg, EVMClient,
  handler, HTTPClient, HTTPCapability, LAST_FINALIZED_BLOCK_NUMBER, Runner,
  type HTTPPayload, type HTTPSendRequester, type Runtime,
} from "@chainlink/cre-sdk";
import {decodeFunctionResult, encodeFunctionData, parseAbi, toHex, zeroAddress, zeroHash, type Address} from "viem";

type Config = {evidenceOrigin: string};
type Receipt = {
  invoice: string; digest: string; recipient: string; environment: string; chainId: number;
  txHash: string; blockHash: string; logIndex: number; attemptKey: string;
};
type Provider = {attemptKey: string; available: boolean; attempt: string; route: string; simulated: boolean};
type Input = {run: string; receipt: Receipt; scenario: string; name: string; resolver: Address};
type Decision = {run: string; receipt: Receipt; route: "HOLD" | "USE_MUDREX" | "USE_P2P"; reason: string};

const universalResolver = "0x24e1d8e068620b647ca097f961a61055f4f42d72";
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

function fetchEvidence<T>(runtime: Runtime<Config>, path: string): T {
  function fetchBody(requester: HTTPSendRequester, url: string): string {
    const response = requester.sendRequest({url, method: "GET"}).result();
    if (response.statusCode !== 200) throw new Error("Evidence endpoint rejected the request");
    return new TextDecoder().decode(response.body);
  }
  const response = new HTTPClient()
    .sendRequest(runtime, fetchBody, consensusIdenticalAggregation<string>())(runtime.config.evidenceOrigin + path)
    .result();
  return JSON.parse(response) as T;
}

function checkRecipient(runtime: Runtime<Config>, input: Input): boolean {
  const labels = input.name.split(".");
  if (labels.length < 2 || labels.at(-1) !== "eth" ||
      labels.some(label => !/^[a-z0-9-]{1,63}$/.test(label))) return false;
  const name = toHex(Uint8Array.from(labels.flatMap(label => [
    label.length, ...Array.from(label, letter => letter.charCodeAt(0)),
  ]).concat(0)));
  const evm = new EVMClient(16015286601757825753n); // Ethereum Sepolia

  function read(functionName: "hasAddr" | "addr") {
    const profile = encodeFunctionData({abi: resolverABI, functionName, args: [zeroHash, coinType]});
    const data = encodeFunctionData({abi: universalABI, functionName: "resolve", args: [name, profile]});
    const response = evm.callContract(runtime, {
      call: encodeCallMsg({from: zeroAddress, to: universalResolver, data}),
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
  const result = (route: Decision["route"], reason: string): Decision => ({
    run: input.run, receipt: input.receipt, route, reason,
  });
  const id = input.receipt.invoice;
  if (!/^inv_[a-f0-9]{12}$/.test(id) || input.receipt.environment !== "testnet" ||
      input.receipt.chainId !== 1874 || !/^[a-z_]+$/.test(input.scenario)) {
    return result("HOLD", "Requires a Whitechain Sepolia demo invoice");
  }
  try {
    const receipt = fetchEvidence<Receipt>(runtime, "/api/cre/receipt/" + id);
    if (!sameReceipt(receipt, input.receipt)) return result("HOLD", "Settlement evidence changed");
    try {
      if (!checkRecipient(runtime, input)) return result("HOLD", "ENSv2 recipient mismatch or missing record");
    } catch {
      return result("HOLD", "Finalized ENSv2 lookup failed. If the name or record changed recently, wait for Sepolia finality and retry.");
    }
    const provider = fetchEvidence<Provider>(runtime, "/api/cre/provider/" + id + "?scenario=" + input.scenario);
    if (!provider.simulated || provider.attemptKey !== receipt.attemptKey) {
      return result("HOLD", "Provider response does not match the attempt");
    }
    if (provider.attempt === "known") {
      if (provider.route === "p2p") return result("USE_P2P", "Reconcile the existing simulated P2P order");
      if (provider.route === "mudrex" || provider.route === "eu_offramp" || provider.route === "legacy") {
        return result("USE_MUDREX", "Reconcile the existing simulated Mudrex order");
      }
    }
    if (provider.attempt !== "none") return result("HOLD", "Prior payout outcome unknown");
    if (provider.available === true) return result("USE_MUDREX", "Primary is available before dispatch");
    if (provider.available === false) return result("USE_P2P", "Licensed provider not available in this demo (requires identity verification). No order was submitted.");
    return result("HOLD", "Provider availability is missing");
  } catch {
    return result("HOLD", "Settlement or provider evidence unavailable");
  }
}

export async function main() {
  const runner = await Runner.newRunner<Config>();
  await runner.run(() => [handler(new HTTPCapability().trigger({}), onHttpTrigger)]);
}
