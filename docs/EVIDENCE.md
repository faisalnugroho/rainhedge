# RainHedge — Evidence (v2)

All verdicts below are chain-authoritative: read back from the deployed
contract via `get_policy` / `get_stats` (Studionet), tx hashes recorded
in `docs/deployment_log.json` by `scripts/deploy_smoke.py`; deployed-code
identity proven by `scripts/prove_byte_identity.py` (SDK get_transaction
→ sha256 of `contract_code` == repo HEAD).

## Deployment (v2)

- Network: studionet
- Contract: `0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88`
- Deploy tx: `0x14c714c1072def3e170386c283219e5bb1478870eb86af0b8f7775faeac4cf57`
- Deployed code sha256: `7f202ca16fcdb8fc21c1b6b8745c001e89fe3e8e4c100e93228f8e435d7c8a04`
  (byte-identical to `contracts/rainhedge.py` at repo HEAD, 31,598 bytes)
- Explorer: https://explorer-studio.genlayer.com/address/0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88
- dApp (GitHub Pages, bound to v2): https://faisalnugroho.github.io/rainhedge/
- v1 contract (superseded by the v2 audit fixes):
  `0x57806f65a48bEA713500b79E06F6b0D018fcFFcb` — log preserved at
  `docs/deployment_log_v1_0x5780.json`

## Live scenario matrix (v2 smoke, challenge 300 s)

| # | Scenario | Policy id | Verdict | Totals | Proof |
|---|----------|-----------|---------|--------|-------|
| A1 | drought determinism 1 | `drought-1` | PAYOUT | 9.3 / 9.5 mm vs 35 mm | tx in deployment_log |
| A2 | drought determinism 2 | `drought-2` | PAYOUT | 9.3 / 9.5 mm (identical) | tx in deployment_log |
| A3 | drought determinism 3 | `drought-3` | PAYOUT | 9.3 / 9.5 mm (identical) | tx in deployment_log |
| B | wet weeks → refund | `rain-1` | NO_PAYOUT | 83.0 / 82.2 mm | `paid=0`, **`claimable=0`** (v2 fix verified live) |
| C | tampered pin | `tamper-1` | INCONCLUSIVE | — (fail-closed) | labels CONSISTENT/UNVERIFIABLE, digest mismatch |

Final `get_stats` (v2): total=6, payout=4, no_payout=1, inconclusive=1 —
the sixth policy (`video-demo-174651`, PAYOUT, same dry windows and
identical totals) was opened, funded and resolved from the live dApp with
an independent burner wallet during the Oct 6 video recording; its tx
hashes live only on-chain (explorer), not in this log.

Every resolve above settled in a single MAJORITY_AGREE consensus round
(determinism), with the LLM witness labels + verbatim citations sealed
in `result` and the contract deriving the verdict.

## What the scenario matrix proves

- **A1–A3 (PAYOUT ×3, identical totals, single round each):** the
  deterministic measurement layer is node-independent — integer micro-mm
  totals converge exactly across independent validator runs.
- **B (NO_PAYOUT, premium refunded via emit_transfer):** honest data
  over the trigger pays nothing; v2 settles the refund fully at resolve
  (claimable=0), closing the double-claim path the v1 live smoke
  exposed. Verified on-chain post-fix.
- **C (tampered pin → INCONCLUSIVE):** a digest that commits to
  different window bytes fails closed even though the fetched record
  looks valid — underwriting binding is enforced, not assumed.

## Security audit (v1 → v2)

Two issues found by self-audit before this deployment, both fixed with
regression tests (45/45 direct-mode GenVM tests green at the v2 audit;
48/48 after the final pre-submission audit added evidence-robustness
regressions, local + CI):

1. **NO_PAYOUT double-claim** (fund-loss, HIGH): v1 refunded the premium
   at settle but ALSO left `claimable_wei = premium`; `claim_refund`
   checks only `claimable > 0`, so the buyer could draw the same premium
   a second time out of the shared escrow. v1's live `rain-1` carried
   the bug (claimable=0.01 GEN after refund). Fix: NO_PAYOUT zeroes
   claimable at settle; regression test asserts the second claim reverts
   `nothing_claimable`.
2. **Registry griefing** (DoS, MEDIUM): v1 appended the policy id and
   counted exposure at free `open_policy`, so anyone could crowd the
   bounded registry (MAX_POLICIES=100) and the exposure cap with
   never-funded policies. Fix: registry insertion, `registry_full` and
   `exposure_cap_reached` gates moved into `fund_policy` (the admitted,
   paid stake), checks-before-effects; regression test asserts free
   opens stay invisible to `list_policies` / `get_exposure`.

## Off-chain verification

- 48/48 direct-mode GenVM tests (web/LLM boundaries mocked): parametric
  outcomes and threshold boundaries, digest binding (dry pin / wet bytes
  → fail-closed), malformed-evidence and wrong-date fail-closed
  regressions, citation discipline, model dissent, determinism gates,
  refund paths, and the two v2 regressions.
- GitHub Actions CI green on every push (`tests.yml`), Pages deploy
  green (`deploy-pages.yml`).
- genvm-lint 3/3 + SDK validation (Python 3.12 toolchain), rerun on the
  v2 source before deploy.

## E2E on the live dApp (video evidence)

Recorded against the live Pages dApp bound to v2: burner wallet →
faucet → open (pins built in-page over the commit-pinned catalog) →
fund → resolve from the UI → verdict/totals/labels rendered from chain
state → explorer view. Screenshots + ≤30 s assembled video in repo
`docs/` links; recording log at `rainhedge-artifacts/record.log`.
