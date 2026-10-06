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
`open_policy`. The buyer funds the policy with an exact premium into
contract escrow. At resolution — gated by an immutable challenge
deadline — every pinned URL is re-fetched by every validator,
digest-verified, checked against the exact expected day list, and
summed into integer micro-mm totals by contract code. An LLM witness
pass adds per-record provenance labels (CONSISTENT / INCONSISTENT /
UNVERIFIABLE), each backed by verbatim citations re-validated on-chain
against the pinned bytes. The verdict is derived by a pure contract
function: all labels CONSISTENT + complete evidence + every window
total strictly below the trigger → PAYOUT (payout_pct of the escrow to
the buyer); honest data over the trigger → NO_PAYOUT with the premium
refunded in full at settle; anything unproven → INCONCLUSIVE with the
premium claimable back by the buyer. Fail-closed by construction: a
fooled, dissenting, or unavailable model can only ever reduce to
refund, never to a wrong payout.

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
live on the v2 deployment.

Deliverables: 45-test gltest direct-mode suite (local GenVM, mocked
web/LLM boundaries; CI green), live Studionet deployment with a
5-policy honest smoke (PAYOUT ×3 determinism, NO_PAYOUT full-refund,
tampered-pin INCONCLUSIVE), SDK byte-identity proof
(deployed contract_code sha256 == repo HEAD), GitHub Pages dApp with
in-browser pin computation (WebCrypto), burner wallets, faucet, and
chain-authoritative state rendering, plus a ≤30 s video demo recorded
live against the dApp.

## Links
- Repo: https://github.com/faisalnugroho/rainhedge
- Live explorer (contract):
  https://explorer-studio.genlayer.com/address/0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88
- dApp: https://faisalnugroho.github.io/rainhedge/
- Video demo (≤30 s): attached
- Evidence: docs/EVIDENCE.md + docs/deployment_log.json in the repo

## Key evidence (Studionet, chain-authoritative)
- Deploy (MAJORITY_AGREE): contract
  `0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88`, deploy tx
  `0x14c714c1072def3e170386c283219e5bb1478870eb86af0b8f7775faeac4cf57`,
  deployed-code sha256 `7f202ca16fcdb8fc21c1b6b8745c001e89fe3e8e4c100e93228f8e435d7c8a04`
  == repo HEAD (byte identity, SDK get_transaction proof)
- drought-1/2/3: PAYOUT ×3 with IDENTICAL totals (9.3 / 9.5 mm vs
  35 mm trigger), one MAJORITY_AGREE round each — determinism
- rain-1: NO_PAYOUT, totals 83.0 / 82.2 mm, premium refunded via
  emit_transfer, `claimable_wei = 0` (double-claim fix verified live)
- tamper-1: pin digest commits to different window bytes →
  INCONCLUSIVE, fail-closed (underwriting binding enforced)
- 45/45 direct-mode GenVM tests; CI green; v1 audit findings documented
  with regressions in docs/EVIDENCE.md

## Honest limitations
- Cover windows are historical (records final at open time); live
  future windows are the natural product extension.
- Single upstream archive; pins bind to exact canonical bytes, but a
  globally wrong upstream record would be consistently wrong.
  Multi-source pinning is the extension path.
- payout_pct is pro-rata on the escrowed premium in this testnet
  version; pooled underwriting capital is out of scope.
