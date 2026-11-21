"""Compile the demo contracts and the official Chainlink Local router."""
import hashlib
import json
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import solcx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".data" / "ccip-src"
SOLC = "0.8.28"
PACKAGES = (
    ("local", "@chainlink/local", "0.3.1", "2b0d7af86b44acfb32acdb09966286e348fd138488641637488329b58dc05bde"),
    ("ccip", "@chainlink/contracts-ccip", "2.0.0", "59c3ea7be405d68cadd948ac1c8ee5e0b7df4d1cdcde709bf1515e009d5dd759"),
    ("contracts", "@chainlink/contracts", "1.5.0", "24a8d510e947a74763723845d5f55405997104aecb9d45061f969d25fb917a3d"),
    ("oz", "@openzeppelin/contracts", "5.3.0", "18ecbb212e36fa4de9fbf85caed66467bbe7e4cd770d70e674647e4f406c9977"),
)
ARTIFACTS = {"CCIPLocalRouter", "PayoutDecisionSender", "PayoutDecisionReceiver"}


def download_sources():
    CACHE.mkdir(parents=True, exist_ok=True)
    paths = {}
    for alias, package, version, expected_hash in PACKAGES:
        archive = CACHE / f"{alias}.tgz"
        if not archive.exists():
            name = package.rsplit("/", 1)[1]
            with urlopen(f"https://registry.npmjs.org/{package}/-/{name}-{version}.tgz", timeout=30) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError(f"Checksum mismatch for {package}@{version}")
            archive.write_bytes(data)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"Checksum mismatch for {archive}")
        dest = CACHE / alias
        if not dest.exists():
            with TemporaryDirectory(dir=CACHE) as staging:
                with tarfile.open(archive) as tar:
                    tar.extractall(staging, filter="data")
                (Path(staging) / "package").rename(dest)
        paths[alias] = dest
    return paths


def main():
    paths = download_sources()
    if SOLC not in [str(version) for version in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC)
    compiled = solcx.compile_files(
        [ROOT / "contracts/src/PayoutDecisionCCIP.sol", paths["local"] / "src/ccip/CCIPLocalRouter.sol"],
        import_remappings=[
            f"@chainlink/contracts-ccip/={paths['ccip']}/",
            f"@chainlink/contracts/={paths['contracts']}/",
            f"@openzeppelin/contracts@5.3.0/={paths['oz']}/",
        ],
        allow_paths=str(CACHE), solc_version=SOLC, evm_version="cancun",
        optimize=True, via_ir=True, output_values=["abi", "bin"],
    )
    output = ROOT / "contracts" / "out"
    output.mkdir(exist_ok=True)
    for qualified_name, contract in compiled.items():
        name = qualified_name.rsplit(":", 1)[1]
        if name in ARTIFACTS:
            artifact = {"abi": contract["abi"], "bytecode": "0x" + contract["bin"]}
            (output / f"{name}.json").write_text(json.dumps(artifact) + "\n")
    print("Compiled:", ", ".join(sorted(ARTIFACTS)))


if __name__ == "__main__":
    main()
