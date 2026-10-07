# RainHedge

> Parametric rainfall (drought) cover on GenLayer — hash-pinned weather
> records, exact integer measurement, consensus witness, deterministic
> payout. The contract decides; the model only witnesses.

## Why now (trend)

Weather-triggered parametric insurance is the largest and
fastest-standardizing segment of the parametric market (weather & climate
index held ~57% of the global parametric market in 2025; catastrophe and
weather-index products are the growth core through 2026), and DeFi cover
lists parametric payouts as its flagship product class. What on-chain
cover always lacked is an objective, manipulation-resistant trigger:
someone must decide, from data nobody can quietly rewrite, whether the
covered condition happened. That is exactly what GenLayer consensus does.

## Why GenLayer is necessary

"Did rainfall over this exact week at this exact spot stay below 35 mm?"
is an objective question about external data — but an on-chain answer is
only trustworthy if independent validators re-derive it. RainHedge pins
the evidence (sha256 over canonicalized Open-Meteo Archive records) at
underwriting time; at resolution, validators re-fetch the pinned URLs,
re-verify every digest, re-measure totals in exact integer math, and run
an LLM witness pass whose only job is provenance labeling. The verdict is
derived by the CONTRACT from the sealed labels and the measured totals —
never by the model. A fooled or disagreeing model can only ever fail
closed to INCONCLUSIVE, where the premium stays claimable by the buyer.

## Architecture (two independent decision layers)

1. **Deterministic measurement (model-independent)** — every pinned URL
   is fetched, sha256-verified against the on-chain pin, checked for the
   exact expected day list, and summed into integer micro-mm totals.
   Canonicalization (strip the server timing field, integral floats →
   ints, sorted-key JSON) is byte-identical across Python and JavaScript:
   the sha256 of the March 9–15 2026 Jakarta record is
   `6352e857fe0367c9…` from BOTH the dApp builder and the contract.
2. **LLM witness + verbatim citations** — per-record
   CONSISTENT / INCONSISTENT / UNVERIFIABLE provenance labels, each
   non-UNVERIFIABLE label requiring a verbatim quote (2–80 chars)
   re-validated on-chain against the fetched record. The model never sees
   the trigger and never chooses the verdict.

Fail-closed: missing/tampered/unparseable records, model dissent, or a
failed consensus round all yield INCONCLUSIVE — `claim_refund` returns
the premium to the buyer, unproven never silently converts into a kept
premium. NO_PAYOUT refunds the premium in full as part of settlement
(nothing stays claimable — a double-claim path found in a live smoke
and closed by regression test).

**Underwriting binding:** the pin digests are committed in `open_policy`
BEFORE funding. `test_digest_binding_dry_pin_wet_bytes` proves the
resolve-time data must match the pinned bytes — data that merely looks
valid is not enough; tampering fails closed even when the fetched weather
would have paid.

## Live deployment (Studionet)

- Contract: `0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88`
- Deployer: `0x8183965AD0A53EebcD1869C93d794733291cfD10`
- Deploy tx + deployed-code identity in `docs/deployment_log.json`
  (sha256 of the deployed `contract_code` == sha256 of
  `contracts/rainhedge.py` at this repo's HEAD — SDK get_transaction
  proof, not shell RPC)
- dApp: https://faisalnugroho.github.io/rainhedge/
- Data source: `archive-api.open-meteo.com/v1/archive` (open, keyless;
  the ONLY nondeterministic field `generationtime_ms` is stripped by the
  canonical form committed in the pin)

## Verification summary (tx hashes in docs/deployment_log.json)

- 48/48 direct-mode GenVM tests (web/LLM boundaries mocked) — local AND
  GitHub Actions CI green.
- genvm-lint: 3/3 checks + SDK validation passed (Python 3.12 toolchain).
- Live consensus smoke (challenge window 300 s, node clock):
  - drought-payout ×3 — pins over the two driest probed Jakarta weeks
    (9.3 mm and 9.5 mm total vs 35 mm trigger) → **PAYOUT ×3, identical
    totals, single consensus round each** (determinism)
  - rain-refund ×1 — pins over wet weeks (83.0 / 82.2 mm) →
    **NO_PAYOUT**, premium refunded in full via emit_transfer
    (`claimable_wei = 0` — the v2 double-claim fix, verified live)
  - tampered-pin ×1 — one pin's digest commits to different window bytes
    → **INCONCLUSIVE** (fail-closed over valid-looking data)
- Browser E2E on the live dApp: burner wallet → faucet → open → fund →
  resolve from the UI → verdict rendered from chain state.
- Video demo (≤30 s): linked from the repo + submission.

## Honest limitations (by design, not omission)

- Cover windows are HISTORICAL — this version settles on already-final
  records (the honest, verifiable core). Live future windows are a
  product extension: the contract already gates resolution on the
  on-chain challenge deadline only.
- The archive is a single upstream source; a pin binds to its canonical
  bytes, so consensus cannot be fooled by serving different data, but a
  globally wrong upstream record would be consistently wrong everywhere.
  Multi-source pinning is the natural extension.
- PAYOUT percentage is pro-rata on the premium escrow (coverage ×
  payout_pct semantics apply to the escrowed funds in this testnet
  version); real underwriting capital pools are out of scope here.
- INCONCLUSIVE history is preserved on-chain on purpose: unproven never
  passes silently.

## Run it

```bash
# tests (needs Python 3.12 + the genvm runner tarball pre-seeded)
pip install -r requirements-dev.txt
pytest tests/direct/ -q -p no:cacheprovider

# lint (Python 3.12 venv with genvm-linter + genlayer-py)
GENVMROOT=/tmp/genvmroot genvm-lint check contracts/rainhedge.py
```

Frontend: serve `frontend/` or use the GitHub Pages URL. Burner wallets
are generated in-browser; faucet via the sim endpoint; pins are computed
in the page with WebCrypto and verified by every validator.
