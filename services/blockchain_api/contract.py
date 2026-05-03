import json
import os
from pathlib import Path
from web3 import Web3

NODE_URL = os.environ.get("HARDHAT_URL", "http://127.0.0.1:8545")

_CONTRACTS_DIR = Path(
    os.environ.get("CONTRACTS_DIR",
                    str(Path(__file__).parent.parent.parent / "contracts"))
)

_DEPLOYED_JSON = _CONTRACTS_DIR / "deployed.json"

def _get_contract_address() -> str:
    if _DEPLOYED_JSON.exists():
        return json.loads(_DEPLOYED_JSON.read_text())["address"]
    raise FileNotFoundError(
        f"No deployed.json found at {_DEPLOYED_JSON}. "
        "Run: cd contracts && npx hardhat run scripts/deploy.js --network localhost"
    )

ABI_PATH = (
    _CONTRACTS_DIR
    / "artifacts"
    / "contracts"
    / "MedicalAudit.sol"
    / "MedicalAudit.json"
)


def get_web3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(NODE_URL))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Ethereum node at {NODE_URL}")
    return w3


def get_contract():
    w3 = get_web3()
    artifact = json.loads(ABI_PATH.read_text())
    abi = artifact["abi"]
    return w3, w3.eth.contract(
        address=Web3.to_checksum_address(_get_contract_address()),
        abi=abi,
    )