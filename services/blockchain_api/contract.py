import json
from pathlib import Path
from web3 import Web3

NODE_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS = "0xDc64a140Aa3E981100a9becA4E685f962f0cF6C9"

ABI_PATH = (
    Path(__file__).parent.parent.parent
    / "contracts"
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
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=abi,
    )