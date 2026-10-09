# RainHedge — Evidence (v3)

All verdicts below are chain-authoritative: read back from the deployed
contract via `get_policy` / `get_stats` / `get_exposure` (Studionet), tx
hashes recorded in `docs/deployment_log.json` by
`scripts/live_verify_v3.py`. Deployed-source identity is proven by
comparing the node-computed contract schema of the deployed address with
the schema generated from the repo source (both computed by the node —
see "Identity proof" below).

## Deployment (v3)

- Network: studionet (chain_id 0xf22f)
- Contract: `0xE692257eBA224C6231F9368c707a7004657f45DB`
- Deploy: vote=MAJORITY_AGREE exec=SUCCESS (`audit/deploy_v3.log`); the
  raw deploy tx hash was lost to a studio 502 during receipt polling —
  recorded as `deploy_tx: null` in the log, never fabricated. Deploy
  success is evidenced by the live contract state and the schema proof.
- Identity proof: node-computed `get_contract_schema(deployed address)`
  is byte-identical to `get_contract_schema_for_code(repo source at
  HEAD, sha256 88579f6b6b82374e…)` — `schema_identical: true` in
  `deployment_log.json`
- Explorer: https://explorer-studio.genlayer.com/address/0xE692257eBA224C6231F9368c707a7004657f45DB
- dApp (GitHub Pages, bound to v3): https://faisalnugroho.github.io/rainhedge/
- Prior deployments (superseded): v2 `0xA0E9fA8a…3F88`
  (`docs/deployment_log_v2_0xA0E9.json`), v1 `0x57806f65…FFcb`
  (`docs/deployment_log_v1_0x5780.json`)

## v3 changes over v2 (what this deployment adds)

1. **Two-sided funding**: a policy now needs BOTH sides funded before it
   can resolve — the buyer escrows the premium (`fund_policy`), and a
   capital provider escrows the FULL declared coverage
   (`fund_coverage`). Settlement pays from declared coverage, never
   from the premium.
2. **Coordinate binding**: a pin proves the BYTES; the record's own
   latitude/longitude must match the policy's declared location (0.25°
   = one ERA5 grid cell, deterministic integer comparison). A record
   for somewhere else demotes to UNVERIFIABLE → INCONCLUSIVE.
3. **Funder-flow accounting**: after a PAYOUT the buyer receives
   premium + payout immediately at settle; the coverage remainder stays
   `coverage_claimable_wei`, claimable ONLY by the recorded
   `coverage_funder`.

## Live scenario matrix (v3 verification, challenge 300 s)

| # | Scenario | Policy id | Verdict | Proof |
|---|----------|-----------|---------|-------|
| A1–A3 | drought determinism ×3 | `drought-1/2/3` | PAYOUT ×3, identical totals 9.3/9.5 mm vs 35 mm | recorded in deployment_log + run log |
| B | wet weeks | `rain-1` | NO_PAYOUT, `paid=0`, `claimable=0`, full coverage back to the funder | recorded |
| C | tampered pin | `tamper-1` | INCONCLUSIVE (fail-closed), premium refund + coverage claim both completed live | recorded |
| D | unfunded coverage | `nocov-1` | `resolve_policy` reverts `coverage_not_funded`; policy stays ACTIVE | recorded |

Final live state: `get_stats` = {total: 5, payout: 3, no_payout: 1,
inconclusive: 1}; `get_exposure` = 0.6 ETH funded of the 100 ETH cap.
(Policies drought-1..3 and rain-1 completed in an earlier run of the
same verification script that crashed mid-way on studio 502s; the
idempotent resume re-verified every verdict and invariant on-chain.)

## V3 accounting proof (chain-read)

- drought-1 PAYOUT: `paid_wei` = 8e16 = exactly coverage × payout_pct
  (80%); `claimable_wei` = 0; conservation
  `premium + coverage == buyer_out + funder_out` holds.
- **Funder-guard addendum** (`live_addendum_funder_guard` in the log,
  `scripts/live_v3_addendum.py`, all steps with real tx hashes on
  drought-2): a fresh burner wallet attempting `claim_coverage` is
  reverted `only_the_funder_can_claim`; the recorded funder then claims
  exactly 2e16 wei (post-claim `coverage_claimable_wei` = 0); a double
  claim reverts `nothing_claimable`.
- NO_PAYOUT (rain-1): premium refunded at settle, full coverage 1e17
  claimable by and claimed by the funder.
- INCONCLUSIVE (tamper-1): BOTH sides fully restituted live — buyer
  `claim_refund` of the premium + funder `claim_coverage` of the full
  coverage; second attempts revert `nothing_claimable`.

## Security audit history (v1 → v2 → v3)

1. **NO_PAYOUT double-claim** (fund-loss, HIGH; v1): fixed in v2 —
   NO_PAYOUT zeroes claimable at settle; regression asserts the second
   claim reverts.
2. **Registry griefing** (DoS, MEDIUM; v1): fixed in v2 — registry
   insertion and the exposure-cap gate moved into `fund_policy`;
   regression asserts free opens stay invisible to `list_policies` /
   `get_exposure`.
3. **Premium-funded payout** (design, v2): v2 paid from the premium
   escrow; v3 moves to declared-coverage settlement with a dedicated
   capital provider, enforced by the `coverage_not_funded` resolve gate
   (proven live, scenario D).

## Off-chain verification

- 62/62 direct-mode GenVM tests (web/LLM boundaries mocked): parametric
  outcomes and threshold boundaries, digest binding, coordinate
  binding, malformed-evidence and wrong-date fail-closed regressions,
  citation discipline, model dissent, determinism gates, refund paths,
  the v2 regressions, and the v3 two-sided funding/funder-guard paths.
- genvm-lint 3/3 on the v3 source; GitHub Actions CI green on every
  push (`tests.yml`), Pages deploy green (`deploy-pages.yml`).
- Run logs preserved in-repo: `audit/deploy_v3.log`,
  `audit/live_v3.log`, `audit/live_v3b.log`, `audit/live_v3c.log`,
  `audit/live_verify_final.log`.

## E2E on the live dApp (video evidence)

The demo video (docs/rainhedge-demo.mp4, 25.1 s) was recorded against
the LIVE v3 Pages dApp (fund tabs, contract 0xE692…45DB): burner wallet
→ open → two-sided funding (premium escrow, then coverage escrow by the
capital provider — order enforced by the contract: coverage without
premium reverts `fund_premium_first`) → resolve after the challenge
window → PAYOUT verdict rendered from chain state → explorer view.
Every step is chain-authoritative: the capture script waits for the
on-chain state (not page receipts) before each screenshot. Full tx
hashes for the recorded policy `video-demo-v3-034146` (open /
fund_policy / fund_coverage / resolve) are in `docs/demo_video_txs.json`;
the resolved policy reads PAYOUT with totals 9.3 / 9.5 mm and
`paid_wei = 0.08 ETH` on-chain.
