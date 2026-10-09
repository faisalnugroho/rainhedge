#!/usr/bin/env python3
"""Live addendum to the v3 verification: the wrong-claimant guard for
claim_coverage.

The main run (audit/live_verify_final.log) resumed past drought-1 whose
coverage remainder had already been claimed by an earlier (crashed) run,
so the burner-tries-to-claim guard executed nowhere on-chain. drought-2
resolved PAYOUT with its 2e16 wei remainder still unclaimed, which makes
the full guard sequence provable here with real tx hashes:

  1. a fresh burner claims drought-2 coverage  -> revert
     only_the_funder_can_claim
  2. the recorded funder claims it             -> SUCCESS, exactly 2e16
  3. double claim                              -> revert nothing_claimable

Appends the evidence to docs/deployment_log.json under
"live_addendum_funder_guard" (idempotent: skips if already present).
"""
import json
import time
from pathlib import Path

from genlayer_py import create_client, create_account
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

ADDR = "0xE692257eBA224C6231F9368c707a7004657f45DB"
KEYFILE = Path("scripts/smoke_deployer.json")
LOG_PATH = Path("docs/deployment_log.json")
REST_WEI = str(int(10 ** 17) - int(10 ** 17) * 80 // 100)  # 2e16


def retry(fn, *a, **kw):
    for attempt in range(1, 6):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if not any(k in msg for k in ("Expecting value", "502", "503",
                                          "429", "timeout", "Timed out",
                                          "Connection", "invalid JSON")) \
                    or attempt == 5:
                raise
            print("  [retry %d] %s" % (attempt, msg[:100]), flush=True)
            time.sleep(3 * attempt)


def wait_final(client, tx, label, strict=True):
    r = retry(client.wait_for_transaction_receipt, transaction_hash=tx,
              status=TransactionStatus.FINALIZED, retries=100, interval=3000)
    lead = ((r.get("consensus_data") or {}).get("leader_receipt") or [{}])
    lead = lead[0] if lead else {}
    execr = r.get("tx_execution_result_name") or lead.get("execution_result")
    vote = r.get("result_name") or "UNKNOWN"
    res = lead.get("result") or {}
    reason = str(res.get("payload") or "") if res.get("status") == "rollback" \
        else ""
    ok = execr in (None, "SUCCESS", "FINISHED_WITH_RETURN") and \
        vote in ("MAJORITY_AGREE", None)
    print("[%s] vote=%s exec=%s ok=%s%s"
          % (label, vote, execr, ok,
             (" reason=" + reason) if reason else ""), flush=True)
    if strict and not ok:
        raise RuntimeError("%s failed" % label)
    return {"ok": ok, "reason": reason}


def read_policy(client, pid):
    return json.loads(retry(client.read_contract, address=ADDR,
                            function_name="get_policy", args=[pid]))


def main():
    acct = json.loads(KEYFILE.read_text())
    signer = create_account(account_private_key=acct["private_key"])
    client = create_client(chain=studionet, account=signer)
    client.local_account = signer

    log = json.loads(LOG_PATH.read_text())
    if "live_addendum_funder_guard" in log:
        print("addendum already present, nothing to do")
        return
    p = read_policy(client, "drought-2")
    assert int(p["coverage_claimable_wei"]) == int(REST_WEI), \
        "drought-2 remainder not intact: %s" % p["coverage_claimable_wei"]
    assert p.get("coverage_funder"), "no funder recorded"

    burner = create_account()
    print("burner:", burner.address, flush=True)
    try:
        retry(client.fund_account, burner.address, 5 * 10 ** 18)
    except Exception as e:  # noqa: BLE001
        print("faucet failed (continuing):", str(e)[:100], flush=True)

    def w(acctobj, fn, args, value=0):
        return retry(client.write_contract, address=ADDR, function_name=fn,
                     args=args, account=acctobj, value=value)

    # 1. wrong claimant MUST be refused
    tx1 = w(burner, "claim_coverage", ["drought-2"])
    g1 = wait_final(client, tx1, "claim_coverage#burner", strict=False)
    assert g1["ok"] is False, "burner claim did NOT revert"
    assert g1["reason"] == "only_the_funder_can_claim", g1["reason"]

    # 2. the funder claims the remainder
    tx2 = w(signer, "claim_coverage", ["drought-2"])
    wait_final(client, tx2, "claim_coverage#funder")
    p2 = read_policy(client, "drought-2")
    assert int(p2["coverage_claimable_wei"]) == 0, p2

    # 3. double claim MUST be refused
    tx3 = w(signer, "claim_coverage", ["drought-2"])
    g3 = wait_final(client, tx3, "claim_coverage#double", strict=False)
    assert g3["ok"] is False and g3["reason"] == "nothing_claimable", g3

    log["live_addendum_funder_guard"] = {
        "pid": "drought-2",
        "wrong_claimant": {"tx": tx1, "reverted": True,
                           "reason": g1["reason"]},
        "funder_claim": {"tx": tx2, "claimed_wei": REST_WEI,
                         "post_claim_claimable": "0"},
        "double_claim": {"tx": tx3, "reverted": True,
                         "reason": g3["reason"]},
        "why": ("the main run resumed past drought-1 (remainder claimed by "
                "a crashed earlier run), so the funder-guard sequence is "
                "proven here on drought-2 with full tx hashes"),
    }
    LOG_PATH.write_text(json.dumps(log, indent=2, sort_keys=True))
    print("DONE: live_addendum_funder_guard recorded", flush=True)


if __name__ == "__main__":
    main()
