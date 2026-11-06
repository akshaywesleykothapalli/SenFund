"""Compile contracts with solc via py-solc-x. Writes contracts/out/*.json and a standard-JSON input
for explorer verification (contracts/out/SenFundSettlement.standard-input.json)."""
import json
from pathlib import Path

import solcx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "out"
SOLC = "0.8.28"
EVM = "cancun"  # OZ 5.6 uses MCOPY; confirm Whitechain Sepolia accepts Cancun opcodes before deploy


def standard_input(sources: dict[str, str]) -> dict:
    return {
        "language": "Solidity",
        "sources": {name: {"content": src} for name, src in sources.items()},
        "settings": {
            "optimizer": {"enabled": True, "runs": 200},
            "evmVersion": EVM, "viaIR": True,
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"]}},
        },
    }


def collect(entry: Path) -> dict[str, str]:
    """Flatten the import graph into standard-JSON source names (OpenZeppelin keeps its @ path)."""
    nm = ROOT / "contracts" / "node_modules"
    todo, seen = [entry], {}
    while todo:
        p = todo.pop()
        name = str(p.relative_to(nm)) if nm in p.parents else str(p.relative_to(ROOT / "contracts"))
        if name in seen:
            continue
        src = p.read_text()
        seen[name] = src
        for line in src.splitlines():
            line = line.strip()
            if line.startswith("import") and '"' in line:
                imp = line.split('"')[1]
                todo.append((nm / imp) if imp.startswith("@") else (p.parent / imp).resolve())
    return seen


def compile_all() -> dict:
    if SOLC not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC)
    OUT.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for entry in [ROOT / "contracts/src/SenFundSettlement.sol", ROOT / "contracts/test/TestTokens.sol"]:
        si = standard_input(collect(entry))
        res = solcx.compile_standard(si, solc_version=SOLC)
        for fname, contracts in res["contracts"].items():
            if fname.startswith("@openzeppelin"):
                continue
            for cname, c in contracts.items():
                artifacts[cname] = {"abi": c["abi"], "bytecode": "0x" + c["evm"]["bytecode"]["object"]}
                (OUT / f"{cname}.json").write_text(json.dumps(artifacts[cname], indent=1))
        if entry.name == "SenFundSettlement.sol":
            (OUT / "SenFundSettlement.standard-input.json").write_text(json.dumps(si, indent=1))
    return artifacts


if __name__ == "__main__":
    print("compiled:", ", ".join(compile_all()))
