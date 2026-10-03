#!/usr/bin/env python3
"""Prove deployed==repo byte identity from the deploy tx.

Fetches the deploy transaction via the SDK's get_transaction (NOT raw RPC
through a shell — that path elides the large base64 contract_code with a
literal '...' mid-string, live-verified ToolGuard lesson), sha256's the
decoded contract_code, and compares it with sha256 of the repo source.
Appends the proof to docs/deployment_log.json (pure addition).
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

from genlayer_py import create_client, create_account
from genlayer_py.chains import studionet

LOG = Path("docs/deployment_log.json")
KEYFILE = Path("scripts/smoke_deployer.json")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    log = json.loads(LOG.read_text())
    deploy_tx = log["deploy"]["tx_hash"]
    address = log["deploy"]["address"]
    code = Path("contracts/rainhedge.py").read_text()

    key = json.loads(KEYFILE.read_text())
    reader = create_account(account_private_key=key["private_key"])
    client = create_client(chain=studionet, account=reader)
    client.local_account = reader

    tx = client.get_transaction(transaction_hash=deploy_tx)
    data = tx.get("data") or {}
    code_b64 = data.get("contract_code")
    assert code_b64, "deploy tx carries no contract_code"
    deployed_source = base64.b64decode(code_b64).decode("utf-8")
    onchain = hashlib.sha256(deployed_source.encode()).hexdigest()
    repo = sha(code)
    proof = {
        "deploy_tx": deploy_tx,
        "address": address,
        "method": ("genlayer_py get_transaction -> data.contract_code "
                   "(base64 of deployed Python source), sha256 compared "
                   "with contracts/rainhedge.py at this repo's HEAD"),
        "bytes": len(deployed_source.encode()),
        "onchain_sha256": onchain,
        "repo_sha256": repo,
        "match": onchain == repo,
    }
    print(json.dumps(proof, indent=2))
    assert proof["match"], "deployed code != repo code"
    # pure-addition append with roundtrip check
    before = LOG.read_text()
    updated = json.loads(before)
    updated["byte_identity_proof"] = proof
    after = json.dumps(updated, indent=2)
    assert json.loads(after) == updated
    LOG.write_text(after)
    print("byte-identity proof appended to", LOG)


if __name__ == "__main__":
    main()
