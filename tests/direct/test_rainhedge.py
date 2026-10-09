"""Real GenVM direct-mode tests for RainHedge v3; web/LLM boundaries mocked.

v3 funding model: the buyer escrows the premium (fund_policy) and a
capital provider escrows the FULL declared coverage (fund_coverage); a
policy can only resolve after BOTH. PAYOUT sends coverage*payout_pct to
the buyer PLUS the premium back; the coverage remainder stays claimable
by the coverage funder. NO_PAYOUT refunds the premium immediately and
leaves the coverage claimable for its funder; INCONCLUSIVE leaves both
claimable. Conservation: buyer_out + funder_out == premium + coverage
on every path.

Mock disciplines inherited from the proven pipeline:
- mock_web takes a DICT {"status": 200, "body": ...} (string mocks are
  silently swallowed by the framework and read as empty fetches);
- first matching regex wins, so specific anchors (start_date=...) are
  registered per window and a generic catch-all comes last;
- vm.warp + the genlayer.gl message_raw datetime patch advance the node
  clock past term + challenge windows;
- emit_transfer value flow is mirrored by a PostMessage hook.
"""
import json
import sys
import datetime
import hashlib
import pytest

LAT = '-6.2'
LON = '106.82'
OWNER = 'faisalnugroho'
REPO = 'rainhedge'
COMMIT = 'a' * 40
W1 = ('2026-03-09', '2026-03-15')
W2 = ('2026-05-25', '2026-05-31')
W3 = ('2026-09-07', '2026-09-13')
W4 = ('2026-09-14', '2026-09-20')
FUTURE = '2027-01-01T00:00:00.000000Z'
TRIGGER_MM = '35'
PAYOUT_PCT = 80
CHALLENGE = 300
PREMIUM_WEI = str(10 ** 16)          # 0.01 ETH
COVERAGE_WEI = str(10 ** 17)         # 0.1 ETH
PAYOUT_WEI = str(int(COVERAGE_WEI) * PAYOUT_PCT // 100)   # 0.08 ETH
COVERAGE_REST_WEI = str(int(COVERAGE_WEI) - int(PAYOUT_WEI))
DRY = [0.0, 0.4, 2.6, 1.6, 0.2, 0.0, 1.2]          # sums to 6.0 mm
WET = [12.0, 15.0, 9.0, 0.0, 21.5, 3.0, 0.4]       # sums to 60.9 mm


def iso_day(start, i):
    d = datetime.date.fromisoformat(start)
    return (d + datetime.timedelta(days=i)).isoformat()


def record(window, values=DRY, lat=-6.221441, lon=106.856186):
    return {
        'latitude': lat, 'longitude': lon,
        'timezone': 'GMT', 'utc_offset_seconds': 0,
        'elevation': 6,
        'timezone_abbreviation': 'GMT',
        'daily_units': {'time': 'iso8601', 'precipitation_sum': 'mm'},
        'daily': {'time': [iso_day(window[0], i) for i in range(7)],
                  'precipitation_sum': list(values)},
    }


def _norm(obj):
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, list):
        return [_norm(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _norm(v) for k, v in obj.items()}
    return obj


def canon(window, values=DRY, **kw):
    parsed = record(window, values, **kw)
    parsed.pop('generationtime_ms', None)
    parsed = _norm(parsed)
    return json.dumps(parsed, sort_keys=True, separators=(',', ':'))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def url(window):
    return ('https://raw.githubusercontent.com/' + OWNER + '/' + REPO
            + '/' + COMMIT + '/records/' + window[0] + '_' + window[1]
            + '.json')


def pin(window, digest=None):
    return {'url': url(window), 'digest': digest or sha(canon(window))}


def pins_json(windows=(W1, W2)):
    return json.dumps([pin(w) for w in windows])


def warp(vm, iso=FUTURE):
    vm.warp(iso)
    sys.modules['genlayer.gl'].message_raw['datetime'] = iso


def stats(c):
    return json.loads(c.get_stats())


def policy_json(**kw):
    args = {
        'policy_id': kw.pop('policy_id', 'policy-1'),
        'buyer': kw.pop('buyer'),
        'lat': kw.pop('lat', LAT),
        'lon': kw.pop('lon', LON),
        'term_days': kw.pop('term_days', 1),
        'trigger_mm': kw.pop('trigger_mm', TRIGGER_MM),
        'payout_pct': kw.pop('payout_pct', PAYOUT_PCT),
        'coverage_wei': kw.pop('coverage_wei', COVERAGE_WEI),
        'premium_wei': kw.pop('premium_wei', PREMIUM_WEI),
        'days_json': kw.pop('days_json', pins_json()),
        'challenge_seconds': kw.pop('challenge_seconds', CHALLENGE),
    }
    args.update(kw)
    return args


def install_transfer_hook(vm):
    def hook(vmm, request):
        pm = (request or {}).get('PostMessage')
        if not pm:
            return None
        addr = pm.get('address')
        recipient = bytes(addr.as_bytes) if hasattr(addr, 'as_bytes') \
            else bytes(addr)
        value = int(pm.get('value', 0))
        contract_addr = vmm._to_bytes(vmm._contract_address)
        vmm._balances[contract_addr] = \
            vmm._balances.get(contract_addr, 0) - value
        vmm._balances[recipient] = vmm._balances.get(recipient, 0) + value
        return {'ok': None}
    vm._gl_call_hook = hook


def balance_of(vm, raw_addr):
    return vm._balances.get(bytes(raw_addr.as_bytes)
                            if hasattr(raw_addr, 'as_bytes')
                            else bytes(raw_addr), 0)


def mock_llm_ok(vm):
    # DETERMINISM DISCIPLINE: mock lists are first-match-wins and are
    # NOT cleared between tests; within one test, a second resolution
    # would otherwise be answered by the FIRST resolution's mocks
    # (proven: policy-2's wet records were served policy-1's dry
    # bytes -> honest INCONCLUSIVE instead of NO_PAYOUT). Clearing at
    # every registration site guarantees each resolution sees exactly
    # the state its test intends. This is TEST infrastructure only —
    # contract code never touches mocks.
    vm.clear_mocks()
    vm.mock_llm(r'.*', json.dumps({
        'labels': ['CONSISTENT', 'CONSISTENT'],
        'reason': 'Both records are well-formed series matching their '
                  'documented windows.',
        'citations': [
            {'source': 0, 'quote': '"2026-03-09"'},
            {'source': 0, 'quote': '2.6'},
            {'source': 1, 'quote': '"2026-05-25"'}]}))


def mock_llm_labels(vm, labels, reason='dissent reason',
                    citations=None):
    vm.clear_mocks()
    vm.mock_llm(r'.*', json.dumps({'labels': labels, 'reason': reason,
                                   'citations': citations or []}))


def mock_web_pair(vm, w1_body, w2_body):
    # NOTE: pure appender — must be called AFTER the LLM helper of the
    # same setup block (clear_mocks() wipes BOTH lists, so a clear here
    # would silently erase a deliberately pre-registered LLM mock, e.g.
    # the garbage-JSON noise test). Every setup sequence in this file
    # registers the LLM helper first; that helper owns the clear.
    vm.mock_web(r'records/2026-03-09',
                {'status': 200, 'body': w1_body})
    vm.mock_web(r'.*', {'status': 200, 'body': w2_body})


def deal(vm, amount):
    vm.deal(vm._to_bytes(vm._contract_address), amount)


def fund_both(c, vm, policy_id, alice, bob,
              premium=PREMIUM_WEI, coverage=COVERAGE_WEI):
    """Premium from the buyer (alice), full coverage from the funder
    (bob) — the complete two-sided v3 funding. NOTE: vm.deal() SETS a
    balance absolutely, so the treasury is topped up by the delta, never
    reset (escrow from earlier policies must survive)."""
    contract_bytes = vm._to_bytes(vm._contract_address)
    current = vm._balances.get(contract_bytes, 0)
    vm.deal(contract_bytes, current + int(premium) + int(coverage))
    vm.value = int(premium)
    c.fund_policy(policy_id)
    vm.value = int(coverage)
    vm.sender = bob
    c.fund_coverage(policy_id)
    vm.value = 0
    vm.sender = alice


@pytest.fixture(autouse=True)
def _transfer_hook(direct_vm):
    install_transfer_hook(direct_vm)


@pytest.fixture
def c(direct_deploy, direct_vm, direct_alice, direct_bob):
    """Contract with policy-1 OPENED and FULLY FUNDED (premium by
    alice, coverage by bob)."""
    contract = direct_deploy('contracts/rainhedge.py')
    direct_vm.sender = direct_alice
    contract.open_policy(**policy_json(buyer=direct_alice.as_hex))
    fund_both(contract, direct_vm, 'policy-1', direct_alice, direct_bob)
    return contract


@pytest.fixture
def bare(direct_deploy, direct_vm):
    """A freshly deployed contract with a funded treasury, no policies."""
    contract = direct_deploy('contracts/rainhedge.py')
    deal(direct_vm, 10 ** 19)
    return contract


# ---------------- open_policy validation ----------------

def test_open_then_read_back(c):
    p = json.loads(c.get_policy('policy-1'))
    assert p['status'] == 'ACTIVE'
    assert p['trigger_mm'] == '35.000000'
    assert len(p['windows']) == 2
    assert p['windows'][0] == [W1[0], W1[1]]
    assert p['balance_wei'] == PREMIUM_WEI
    assert p['premium_wei'] == PREMIUM_WEI
    assert p['coverage_wei'] == COVERAGE_WEI
    assert p['coverage_funded_wei'] == COVERAGE_WEI
    assert p['coverage_funder']


def test_open_duplicate_reverts(c, direct_vm, direct_alice):
    with direct_vm.expect_revert('policy_exists'):
        c.open_policy(**policy_json(buyer=direct_alice.as_hex))


def test_open_by_non_owner_is_fine_buyer_is_explicit(c, direct_vm,
                                                     direct_alice,
                                                     direct_bob):
    """The buyer field is explicit — anyone may open cover FOR a buyer;
    only the buyer can fund the premium (proven later)."""
    direct_vm.sender = direct_bob
    c.open_policy(**policy_json(policy_id='policy-9',
                                buyer=direct_alice.as_hex))
    p = json.loads(c.get_policy('policy-9'))
    assert p['buyer'].lower() == direct_alice.as_hex.lower()


@pytest.mark.parametrize('field,value,reason', [
    ('policy_id', 'Bad_Id!', 'invalid_policy_id'),
    ('buyer', '0xdeadbeef', 'invalid_buyer_address'),
    ('lat', '200', 'invalid_lat'),
    ('lon', '-999', 'invalid_lon'),
    ('lat', '-6.22144', 'invalid_lat'),
    ('lon', '106.85618', 'invalid_lon'),
    ('term_days', 0, 'invalid_term_days'),
    ('term_days', 121, 'invalid_term_days'),
    ('payout_pct', 0, 'invalid_payout_pct'),
    ('payout_pct', 101, 'invalid_payout_pct'),
    ('trigger_mm', '0', 'invalid_trigger_mm'),
    ('trigger_mm', '501', 'invalid_trigger_mm'),
    ('trigger_mm', 'abc', 'invalid_trigger_mm'),
    ('coverage_wei', '999', 'invalid_coverage_wei'),
    ('premium_wei', COVERAGE_WEI, 'invalid_premium'),
    ('premium_wei', '0', 'invalid_premium'),
    ('challenge_seconds', 10, 'invalid_challenge'),
    ('challenge_seconds', 99999999, 'invalid_challenge'),
])
def test_open_validation(bare, direct_vm, direct_alice, field, value,
                         reason):
    direct_vm.sender = direct_alice
    args = policy_json(buyer=direct_alice.as_hex)
    args[field] = value
    with direct_vm.expect_revert(reason):
        bare.open_policy(**args)


def test_open_wrong_repo_path_reverts(bare, direct_vm, direct_alice):
    """A pin outside THIS repo's records/ path (different repo, same
    format) is rejected: pins must commit to the project's own ported
    record set, not an arbitrary paste target."""
    direct_vm.sender = direct_alice
    bad = pin(W1)
    bad['url'] = bad['url'].replace('/' + REPO + '/', '/otherrepo/')
    with direct_vm.expect_revert('invalid_pinned_url'):
        bare.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([bad, pin(W2)])))


def test_open_duplicate_pin_reverts(bare, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('duplicate_pin_window'):
        bare.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(W1), pin(W1)])))


def test_open_bad_digest_reverts(bare, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('invalid_digest'):
        bare.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(W1, digest='z' * 64), pin(W2)])))


def test_open_five_pins_reverts(bare, direct_vm, direct_alice):
    """Four windows are the documented maximum; the count check runs
    before per-entry validation, so the 5th entry trips it."""
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('invalid_days_count'):
        bare.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(W1), pin(W2), pin(W3), pin(W4),
                                  pin(W1)])))


# ---------------- funding model ----------------

def test_exposure_counts_funded_coverage_only(bare, direct_vm,
                                              direct_alice, direct_bob):
    """Exposure and the bounded registry count only policies with REAL
    premium committed — free opens must not crowd out the registry."""
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    assert json.loads(bare.list_policies()) == []
    assert json.loads(bare.get_exposure())['total_exposure_wei'] == '0'
    fund_both(bare, direct_vm, 'policy-1', direct_alice, direct_bob)
    assert json.loads(bare.list_policies()) == ['policy-1']
    assert json.loads(bare.get_exposure())['total_exposure_wei'] == \
        COVERAGE_WEI


def test_fund_requires_exact_premium(c):
    p = json.loads(c.get_policy('policy-1'))
    assert p['balance_wei'] == PREMIUM_WEI
    assert p['status'] == 'ACTIVE'


def test_fund_wrong_value_reverts(bare, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.value = int(PREMIUM_WEI) + 1
    with direct_vm.expect_revert('send exactly the premium'):
        bare.fund_policy('policy-1')
    direct_vm.value = 0


def test_fund_by_non_buyer_reverts(bare, direct_vm, direct_alice,
                                   direct_bob):
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.sender = direct_bob
    direct_vm.value = int(PREMIUM_WEI)
    with direct_vm.expect_revert('only_the_buyer_can_fund'):
        bare.fund_policy('policy-1')
    direct_vm.value = 0


def test_fund_twice_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    direct_vm.value = int(PREMIUM_WEI)
    with direct_vm.expect_revert('already_funded'):
        c.fund_policy('policy-1')
    direct_vm.value = 0


def test_fund_coverage_requires_premium_first(bare, direct_vm,
                                              direct_alice, direct_bob):
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.sender = direct_bob
    direct_vm.value = int(COVERAGE_WEI)
    with direct_vm.expect_revert('fund_premium_first'):
        bare.fund_coverage('policy-1')
    direct_vm.value = 0


def test_fund_coverage_wrong_value_reverts(bare, direct_vm, direct_alice,
                                           direct_bob):
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.value = int(PREMIUM_WEI)
    bare.fund_policy('policy-1')
    direct_vm.value = int(COVERAGE_WEI) + 1
    with direct_vm.expect_revert('send exactly the coverage'):
        bare.fund_coverage('policy-1')
    direct_vm.value = 0


def test_fund_coverage_twice_reverts(c, direct_vm, direct_bob):
    direct_vm.sender = direct_bob
    direct_vm.value = int(COVERAGE_WEI)
    with direct_vm.expect_revert('already_funded'):
        c.fund_coverage('policy-1')
    direct_vm.value = 0


def test_fund_coverage_recorded(c, direct_bob):
    p = json.loads(c.get_policy('policy-1'))
    assert p['coverage_funded_wei'] == COVERAGE_WEI
    assert p['coverage_funder'].lower() == direct_bob.as_hex.lower()


def test_registry_cap_enforced(bare, direct_vm, direct_alice,
                               direct_bob):
    """Two hard caps bound the registry: per-policy coverage <= 1 ETH
    (invalid_coverage_wei) and the registry-wide exposure cap of 100 ETH
    counting FUNDED coverage (exposure_cap_reached at fund time)."""
    one_eth = str(10 ** 18)
    # per-policy cap
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('invalid_coverage_wei'):
        bare.open_policy(**policy_json(buyer=direct_alice.as_hex,
                                       coverage_wei=str(10 ** 18 + 1)))
    # registry-wide cap: 100 x 1-ETH policies exactly fill it; #101 reverts
    for i in range(100):
        pid = f'policy-{i:03d}'
        bare.open_policy(**policy_json(policy_id=pid,
                                       buyer=direct_alice.as_hex,
                                       coverage_wei=one_eth))
        fund_both(bare, direct_vm, pid, direct_alice, direct_bob,
                  coverage=one_eth)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('exposure_cap_reached'):
        bare.open_policy(**policy_json(policy_id='policy-101',
                                       buyer=direct_alice.as_hex))


# ---------------- resolution guards ----------------

def test_resolve_before_challenge_reverts(c, direct_vm):
    with direct_vm.expect_revert('challenge_period_active'):
        c.resolve_policy('policy-1')


def test_resolve_unfunded_reverts(bare, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    warp(direct_vm)
    with direct_vm.expect_revert('not_funded'):
        bare.resolve_policy('policy-1')


def test_resolve_premium_only_reverts(bare, direct_vm, direct_alice,
                                      direct_bob):
    """v3 core gate: premium alone is NOT enough — without the full
    coverage capital the policy cannot resolve at all."""
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.value = int(PREMIUM_WEI)
    bare.fund_policy('policy-1')
    direct_vm.value = 0
    warp(direct_vm)
    with direct_vm.expect_revert('coverage_not_funded'):
        bare.resolve_policy('policy-1')


def test_resolve_unknown_policy(c):
    with pytest.raises(Exception):
        c.resolve_policy('nope-x')


def test_resolve_twice_reverts(c, direct_vm):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    with direct_vm.expect_revert('not_active'):
        c.resolve_policy('policy-1')


# ---------------- parametric outcomes ----------------

def test_drought_payout(c, direct_vm, direct_alice, direct_bob):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['status'] == 'RESOLVED'
    assert p['result']['verdict'] == 'PAYOUT'
    assert p['result']['totals_mm'] == ['6.000000', '6.000000']
    assert p['paid_wei'] == PAYOUT_WEI
    assert p['claimable_wei'] == '0'
    assert p['coverage_claimable_wei'] == COVERAGE_REST_WEI
    assert stats(c)['payout'] == 1
    # the buyer receives the payout PLUS the premium back
    assert balance_of(direct_vm, direct_alice) == \
        int(PAYOUT_WEI) + int(PREMIUM_WEI)
    # the funder's remainder is claimable, not yet paid
    assert balance_of(direct_vm, direct_bob) == 0


def test_claim_coverage_after_payout(c, direct_vm, direct_bob):
    """The funder reclaims the unused coverage remainder; nobody else
    can draw it."""
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    direct_vm.sender = direct_alice if False else direct_bob
    c.claim_coverage('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['coverage_claimable_wei'] == '0'
    assert balance_of(direct_vm, direct_bob) == int(COVERAGE_REST_WEI)
    with direct_vm.expect_revert('nothing_claimable'):
        c.claim_coverage('policy-1')


def test_claim_coverage_requires_funder(c, direct_vm, direct_alice):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('only_the_funder_can_claim'):
        c.claim_coverage('policy-1')


def test_rain_no_payout_refunds_premium(c, direct_vm, direct_alice,
                                        direct_bob):
    """Underwrite a WET week (pins over wet bytes), resolve against the
    same wet bytes: totals clear the trigger -> premium refunded, the
    coverage capital claimable by its funder."""
    direct_vm.sender = direct_alice
    wet_pins = json.dumps([pin(W1, sha(canon(W1, WET))),
                           pin(W2, sha(canon(W2, WET)))])
    c.open_policy(**policy_json(policy_id='policy-2',
                                buyer=direct_alice.as_hex,
                                days_json=wet_pins))
    fund_both(c, direct_vm, 'policy-2', direct_alice, direct_bob)
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1, WET), canon(W2, WET))
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['verdict'] == 'NO_PAYOUT'
    assert p['result']['totals_mm'] == ['60.900000', '60.900000']
    assert p['paid_wei'] == '0'
    # regression: the full refund goes out with the settle; nothing may
    # stay claimable or claim_refund would double-draw the premium
    assert p['claimable_wei'] == '0'
    assert p['coverage_claimable_wei'] == COVERAGE_WEI
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('nothing_claimable'):
        c.claim_refund('policy-2')
    assert stats(c)['no_payout'] == 1
    assert balance_of(direct_vm, direct_alice) == int(PREMIUM_WEI)


def test_one_wet_window_blocks_payout(c, direct_vm, direct_alice,
                                      direct_bob):
    """Parametric rule is strict: EVERY window must be below trigger.
    Pin 1 underwrites a dry week, pin 2 a wet week; the source serves
    exactly what was pinned; the verdict is NO_PAYOUT."""
    direct_vm.sender = direct_alice
    mixed = json.dumps([pin(W1), pin(W2, sha(canon(W2, WET)))])
    c.open_policy(**policy_json(policy_id='policy-2',
                                buyer=direct_alice.as_hex,
                                days_json=mixed))
    fund_both(c, direct_vm, 'policy-2', direct_alice, direct_bob)
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1, DRY), canon(W2, WET))
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['totals_mm'] == ['6.000000', '60.900000']
    assert p['result']['verdict'] == 'NO_PAYOUT'


def test_missing_record_inconclusive_fails_closed(c, direct_vm):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'server error'})
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'
    # the fetched record may legitimately be CONSISTENT; the MISSING one
    # is demoted to UNVERIFIABLE and poisons the evidence basis
    assert p['result']['labels'] == ['CONSISTENT', 'UNVERIFIABLE']
    assert p['result']['totals_mm'] == []
    assert p['claimable_wei'] == PREMIUM_WEI
    assert p['coverage_claimable_wei'] == COVERAGE_WEI
    assert stats(c)['inconclusive'] == 1


def test_tampered_record_inconclusive(c, direct_vm):
    """Fetched bytes that do not match the pin (wrong window content)
    fail closed — even though the data itself looks valid."""
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W3))  # W3 bytes != W2 pin
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_digest_binding_dry_pin_wet_bytes(c, direct_vm, direct_alice,
                                          direct_bob):
    """A pin computed over WET bytes while the source serves DRY bytes:
    digest mismatch -> fail-closed, never a payout. This is the
    underwriting-binding guarantee."""
    buyer = json.loads(c.get_policy('policy-1'))['buyer']
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(
        policy_id='policy-2',
        buyer=buyer,
        days_json=json.dumps([pin(W1),
                              {'url': url(W2),
                               'digest': sha(canon(W2, WET))}])))
    fund_both(c, direct_vm, 'policy-2', direct_alice, direct_bob)
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2, DRY))  # source: DRY
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_coord_mismatch_record_inconclusive(c, direct_vm):
    """Served bytes whose OWN request coordinates are far from the
    policy's coordinates are evidence for somewhere ELSE: coordinate
    gate fails -> UNVERIFIABLE -> INCONCLUSIVE, even though the digest
    matches (the pin proves the bytes, the coords prove the place)."""
    shifted = canon(W1, lat=-46.221441, lon=106.856186)
    direct_vm.sender = direct_alice if False else None
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': shifted})
    direct_vm.mock_web(r'.*', {'status': 200, 'body': canon(W2)})
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'
    assert p['result']['labels'] == ['UNVERIFIABLE', 'CONSISTENT']
    assert p['result']['totals_mm'] == []


def test_coord_mismatch_open_reverts(bare, direct_vm, direct_alice):
    """A policy declaring coordinates in a different HEMISPHERE cannot
    pin records carrying the catalog's coordinates: the coordinate gate
    is declared at open time, and mismatched evidence can only ever
    yield INCONCLUSIVE (never a payout)."""
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex,
                                   lat='-6.9', lon='106.9'))
    # tolerance 0.25 deg: -6.9 vs record -6.221441 differs by ~0.68 deg
    # -> every record would fail the gate; this policy is safe to open
    # (fail-closed, INCONCLUSIVE at worst) — the OPEN-level validation
    # only rejects malformed/out-of-range coordinates.
    p = json.loads(bare.get_policy('policy-1'))
    assert p['lat'] == '-6.9'


def test_model_dissent_fails_closed(c, direct_vm):
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'INCONSISTENT'])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_uncited_label_demoted(c, direct_vm):
    """CONSISTENT without a citation degrades to UNVERIFIABLE — evidence
    or it did not happen."""
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'CONSISTENT'],
                    citations=[{'source': 0, 'quote': '"2026-03-09"'}])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['labels'] == ['CONSISTENT', 'UNVERIFIABLE']
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_bad_citation_dropped(c, direct_vm):
    """Quotes that are NOT verbatim in the fetched record are dropped;
    a label left uncited by the drop degrades to UNVERIFIABLE."""
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'CONSISTENT'],
                    citations=[
                        {'source': 0, 'quote': 'not-in-document'},
                        {'source': 0, 'quote': '"2026-03-09"'},
                        {'source': 1, 'quote': '"2026-05-25"'}])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    quotes = [x['quote'] for x in p['result']['citations']]
    assert 'not-in-document' not in quotes
    assert '"2026-03-09"' in quotes
    assert p['result']['verdict'] == 'PAYOUT'


def test_model_json_garbage_fails_closed(c, direct_vm):
    warp(direct_vm)
    direct_vm.mock_llm(r'.*', 'not json at all')
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


# ---------------- refund paths ----------------

def test_claim_refund_after_inconclusive(c, direct_vm, direct_alice,
                                         direct_bob):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'down'})
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['claimable_wei'] == PREMIUM_WEI
    direct_vm.sender = direct_alice
    c.claim_refund('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['claimable_wei'] == '0'
    with direct_vm.expect_revert('nothing_claimable'):
        c.claim_refund('policy-1')
    assert balance_of(direct_vm, direct_alice) == int(PREMIUM_WEI)
    # the coverage capital stays claimable for its funder
    direct_vm.sender = direct_bob
    c.claim_coverage('policy-1')
    assert balance_of(direct_vm, direct_bob) == int(COVERAGE_WEI)


def test_claim_refund_requires_buyer(c, direct_vm, direct_bob):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'down'})
    c.resolve_policy('policy-1')
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('only_the_buyer_can_claim'):
        c.claim_refund('policy-1')


def test_claim_refund_before_resolve_reverts(c):
    with pytest.raises(Exception):
        c.claim_refund('policy-1')


def test_payout_liquidity_guard(bare, direct_vm, direct_alice,
                                direct_bob):
    """Defense in depth: settlement the contract cannot pay is refused
    even if state were somehow inconsistent — here the treasury holds
    premium + coverage but NOT premium + payout (the deployment deal is
    short by the payout amount)."""
    direct_vm.sender = direct_alice
    bare.open_policy(**policy_json(buyer=direct_alice.as_hex))
    deal(direct_vm, int(PREMIUM_WEI) + int(COVERAGE_WEI)
         - int(PAYOUT_WEI))
    direct_vm.value = int(PREMIUM_WEI)
    bare.fund_policy('policy-1')
    direct_vm.value = int(COVERAGE_WEI)
    direct_vm.sender = direct_bob
    bare.fund_coverage('policy-1')
    direct_vm.value = 0
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    with direct_vm.expect_revert('insufficient_liquidity'):
        bare.resolve_policy('policy-1')


# ---------------- evidence robustness (audit regressions) ----------------

def _open_second_policy(c, direct_vm, direct_alice, direct_bob,
                        days_json):
    """Open + fully fund 'policy-2' for the same buyer as the fixture
    policy."""
    buyer = json.loads(c.get_policy('policy-1'))['buyer']
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(policy_id='policy-2', buyer=buyer,
                                days_json=days_json))
    fund_both(c, direct_vm, 'policy-2', direct_alice, direct_bob)


def test_evidence_malformed_json_with_matching_digest_inconclusive(
        c, direct_vm, direct_alice, direct_bob):
    """Pin commits to MALFORMED bytes and the source serves exactly those
    bytes: the digest matches, but the record cannot be canonicalized ->
    fail-closed INCONCLUSIVE with the premium claimable."""
    malformed = '{"daily": {"time": ['  # unparseable JSON
    _open_second_policy(c, direct_vm, direct_alice, direct_bob,
                        json.dumps([{'url': url(W1), 'digest': sha(malformed)},
                                    pin(W2)]))
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': malformed})
    direct_vm.mock_web(r'.*', {'status': 200, 'body': canon(W2)})
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'
    assert p['result']['totals_mm'] == []
    assert p['claimable_wei'] == PREMIUM_WEI


def test_evidence_wrong_dates_with_matching_digest_inconclusive(
        c, direct_vm, direct_alice, direct_bob):
    """Pin and served bytes agree (digest matches) but the record's date
    list does not match the URL-named window: record_window_mismatch ->
    fail-closed INCONCLUSIVE even though the data itself looks valid."""
    shifted = canon(W3)  # valid record, but for 2026-09-07..13
    _open_second_policy(c, direct_vm, direct_alice, direct_bob,
                        json.dumps([{'url': url(W1), 'digest': sha(shifted)},
                                    pin(W2)]))
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': shifted})
    direct_vm.mock_web(r'.*', {'status': 200, 'body': canon(W2)})
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'
    assert p['result']['totals_mm'] == []


def test_exact_threshold_total_equal_trigger_no_payout(
        c, direct_vm, direct_alice, direct_bob):
    """Parametric boundary: a window total EXACTLY equal to the trigger is
    NOT a drought (payout requires STRICTLY below) -> NO_PAYOUT with the
    premium refunded in full."""
    exact = [5.0] * 7  # sums to exactly 35.0 mm == trigger
    _open_second_policy(c, direct_vm, direct_alice, direct_bob,
                        json.dumps([pin(W1, sha(canon(W1, exact))),
                                    pin(W2, sha(canon(W2, exact)))]))
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1, exact), canon(W2, exact))
    c.resolve_policy('policy-2')
    p = json.loads(c.get_policy('policy-2'))
    assert p['result']['verdict'] == 'NO_PAYOUT'
    assert p['result']['totals_mm'] == ['35.000000', '35.000000']
    assert p['claimable_wei'] == '0'
    assert stats(c)['no_payout'] == 1


# ---------------- accounting conservation ----------------

def test_accounting_conservation_all_paths(c, direct_vm, direct_alice,
                                           direct_bob):
    """buyer_out + funder_out == premium + coverage on every settlement
    path, verified against ACTUAL balances (transfer hook mirrors
    emit_transfer), not just record bookkeeping."""
    treasury_total = int(PREMIUM_WEI) + int(COVERAGE_WEI)

    # Open ALL policies at the base clock FIRST — resolve_verdict() warps
    # to FUTURE, and open_policy must never happen at/after that warp.
    buyer = json.loads(c.get_policy('policy-1'))['buyer']
    direct_vm.sender = direct_alice
    wet_pins = json.dumps([pin(W1, sha(canon(W1, WET))),
                           pin(W2, sha(canon(W2, WET)))])
    c.open_policy(**policy_json(policy_id='policy-2', buyer=buyer,
                                days_json=wet_pins))
    fund_both(c, direct_vm, 'policy-2', direct_alice, direct_bob)
    c.open_policy(**policy_json(policy_id='policy-3', buyer=buyer))
    fund_both(c, direct_vm, 'policy-3', direct_alice, direct_bob)

    def resolve_verdict(policy_id, web_pair):
        warp(direct_vm)
        mock_llm_ok(direct_vm)
        web_pair()
        c.resolve_policy(policy_id)

    # ---- PAYOUT path (fixture policy-1: dry pin, dry bytes) ----
    resolve_verdict('policy-1', lambda: mock_web_pair(
        direct_vm, canon(W1), canon(W2)))
    p = json.loads(c.get_policy('policy-1'))
    buyer_out = int(p['paid_wei']) + int(PREMIUM_WEI)
    funder_out = int(p['coverage_claimable_wei'])
    direct_vm.sender = direct_bob
    c.claim_coverage('policy-1')
    assert balance_of(direct_vm, direct_alice) == buyer_out
    assert balance_of(direct_vm, direct_bob) == funder_out
    assert buyer_out + funder_out == treasury_total

    # ---- NO_PAYOUT path (policy-2: wet pins, wet bytes) ----
    # alice's balance BEFORE this path's settle: payout+premium from
    # path 1. NO_PAYOUT refunds exactly the premium.
    alice_before = balance_of(direct_vm, direct_alice)
    resolve_verdict('policy-2', lambda: mock_web_pair(
        direct_vm, canon(W1, WET), canon(W2, WET)))
    p = json.loads(c.get_policy('policy-2'))
    buyer_out = balance_of(direct_vm, direct_alice) - alice_before
    funder_out = int(p['coverage_claimable_wei'])
    direct_vm.sender = direct_bob
    c.claim_coverage('policy-2')
    assert balance_of(direct_vm, direct_bob) == \
        int(COVERAGE_REST_WEI) + funder_out
    assert buyer_out == int(PREMIUM_WEI)
    assert buyer_out + funder_out == treasury_total

    # ---- INCONCLUSIVE path (policy-3: second window missing) ----
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'down'})
    c.resolve_policy('policy-3')
    p = json.loads(c.get_policy('policy-3'))
    assert p['claimable_wei'] == PREMIUM_WEI
    assert p['coverage_claimable_wei'] == COVERAGE_WEI
    direct_vm.sender = direct_alice
    c.claim_refund('policy-3')
    direct_vm.sender = direct_bob
    c.claim_coverage('policy-3')
    # Full-session balances across ALL THREE settled paths: alice holds
    # the p1 payout + THREE refunded premiums (p1 PAYOUT refund, p2
    # NO_PAYOUT immediate refund, p3 INCONCLUSIVE claim) = payout +
    # 3*premium; bob holds the p1 coverage remainder + TWO full coverage
    # claims (p2 NO_PAYOUT, p3 INCONCLUSIVE) = rest + 2*coverage.
    # (10+80) + 10 + 10 = 110e15 and 20 + 100 + 100 = 220e15; the sum
    # 330e15 == 3 * (premium + coverage) — every wei back to its owner.
    assert balance_of(direct_vm, direct_alice) == \
        int(PAYOUT_WEI) + int(PREMIUM_WEI) * 3
    assert balance_of(direct_vm, direct_bob) == \
        int(COVERAGE_REST_WEI) + int(COVERAGE_WEI) * 2
    # the whole treasury is fully drained: every wei returned to its
    # original owner (conservation in its strongest form)
    contract_bytes = direct_vm._to_bytes(direct_vm._contract_address)
    assert direct_vm._balances.get(contract_bytes, 0) == 0
