# RainHedge — Submission Draft (for the Builder Portal)

The owner pastes/attaches these fields manually. Nothing here claims
steward acceptance; every claim is evidence-backed.

## Category
Builder → Projects (Intelligent Contract)

## Title
RainHedge — Parametric Drought Cover

## One-liner
On-chain parametric rainfall insurance: buyers pin exact historical
weather records by sha256 at underwriting, GenLayer validators re-fetch,
re-verify and re-measure them in exact integer math, and the CONTRACT —
never the model — derives PAYOUT / NO_PAYOUT / INCONCLUSIVE from sealed
evidence.

## Full description
RainHedge is a GenLayer Intelligent Contract implementing parametric
drought cover. A buyer picks a location and 1–4 historical rainfall
windows, the dApp canonicalizes the Open-Meteo Archive responses
(strip the only non-deterministic field, integral floats → ints,
sorted-key JSON) and commits each window as a sha256 pin on-chain at
`open_policy`, bound to the policy's declared coordinates (the record's
own lat/lon must fall inside the same 0.25° ERA5 grid cell — a record
for somewhere else is not evidence for here). Underwriting is two-sided
escrow: the buyer funds the exact premium AND a capital provider funds
the FULL declared coverage (`fund_coverage`); resolution is gated on
both sides being funded. At resolution — gated by an immutable
challenge deadline — every pinned URL is re-fetched by every validator,
digest-verified, checked against the exact expected day list and the
coordinate binding, and summed into integer micro-mm totals by contract
code. An LLM witness pass adds per-record provenance labels
(CONSISTENT / INCONSISTENT / UNVERIFIABLE), each backed by verbatim
citations re-validated on-chain against the pinned bytes. The verdict
is derived by a pure contract function: all labels CONSISTENT +
complete evidence + every window total strictly below the trigger →
PAYOUT (payout_pct of the DECLARED COVERAGE to the buyer, immediately);
honest data over the trigger → NO_PAYOUT with the premium refunded in
full at settle; anything unproven → INCONCLUSIVE with both sides
restitutable. The coverage remainder is claimable only by its capital
provider; unproven never converts into kept funds. Fail-closed by
construction: a fooled, dissenting, or unavailable model can only ever
reduce to refund, never to a wrong payout.

Why GenLayer is necessary: "did rainfall stay under 35 mm over this
pinned week?" is an objective question about off-chain data that a
normal smart contract cannot answer, yet custody and settlement must
stay deterministic and trustless. RainHedge draws the line exactly
there — the LLM never moves funds and never chooses the verdict; the
Equivalence Principle compares only stable decision substance (labels,
integer totals, fetch manifest), never model prose.

Security-audited before submission: a NO_PAYOUT double-claim path
(fund-loss) and a free-open registry-griefing vector were found in the
v1 live deployment, fixed, covered by regression tests, and re-proven
live. v3 replaces premium-funded settlement with declared-coverage
settlement from a dedicated capital provider (resolve reverts
`coverage_not_funded` without it), adds coordinate binding, and its
funder-guard (`only_the_funder_can_claim`) is proven live with tx
hashes.

Deliverables: 62-test gltest direct-mode suite (local GenVM, mocked
web/LLM boundaries; CI green), live Studionet deployment with a
5-policy honest smoke (PAYOUT ×3 determinism, NO_PAYOUT full-refund,
tampered-pin INCONCLUSIVE, unfunded-coverage resolve guard), deployed-
source identity proof (node-computed schema of the deployed address ==
schema of the repo source), GitHub Pages dApp with in-browser pin
computation (WebCrypto), burner wallets, faucet, two-sided funding UI,
and chain-authoritative state rendering, plus a ≤30 s video demo
recorded live against the dApp.

## Links
- Repo: https://github.com/faisalnugroho/rainhedge
- Live explorer (contract):
  https://explorer-studio.genlayer.com/address/0xE692257eBA224C6231F9368c707a7004657f45DB
- dApp: https://faisalnugroho.github.io/rainhedge/
- Video demo (26.6 s, in-repo, recorded on the v2 dApp build):
  https://github.com/faisalnugroho/rainhedge/raw/main/docs/rainhedge-demo.mp4
- Evidence: docs/EVIDENCE.md + docs/deployment_log.json in the repo

## Key evidence (Studionet, chain-authoritative)
- Contract `0xE692257eBA224C6231F9368c707a7004657f45DB`, deploy
  MAJORITY_AGREE exec=SUCCESS (audit/deploy_v3.log); identity proven by
  node-computed schema equality between the deployed address and the
  repo source at HEAD (sha256 88579f6b6b82374e…) — the raw deploy tx
  hash was lost to a studio RPC outage and is recorded as null, never
  fabricated
- drought-1/2/3: PAYOUT ×3 with IDENTICAL totals (9.3 / 9.5 mm vs
  35 mm trigger) — determinism
- rain-1: NO_PAYOUT, totals 83.0 / 82.2 mm, premium refunded at settle
  (`claimable_wei = 0`), full coverage returned to the funder
- tamper-1: pin digest commits to different window bytes →
  INCONCLUSIVE, fail-closed; premium refund + coverage claim both
  executed and verified live, double claims revert
- nocov-1: `resolve_policy` without funded coverage reverts
  `coverage_not_funded` — settlement capital is enforced, not assumed
- funder-guard addendum (tx hashes in the log): burner claim reverted
  `only_the_funder_can_claim`, funder claim exact 2e16 wei SUCCESS,
  double claim reverted `nothing_claimable`
- Final `get_stats`: total=5, payout=3, no_payout=1, inconclusive=1;
  exposure 0.6 / 100 ETH cap
- 62/62 direct-mode GenVM tests; genvm-lint 3/3; CI green; v1+v2 audit
  findings documented with regressions in docs/EVIDENCE.md

## Honest limitations
- Cover windows are historical (records final at open time); live
  future windows are the natural product extension.
- Single upstream archive; pins bind to exact canonical bytes, but a
  globally wrong upstream record would be consistently wrong.
  Multi-source pinning is the extension path.
- The ≤30 s demo video was recorded on the v2 dApp build (before the
  v3 two-sided funding UI landed); the live Pages dApp now runs the v3
  frontend bound to the v3 contract.
- Testnet deployment: coverage amounts and the capital-provider role
  are exercised at testnet scale.
