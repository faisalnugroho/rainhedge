"""Real GenVM direct-mode tests for RainHedge; web/LLM boundaries mocked.

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
PREMIUM_WEI = str(10 ** 16)
COVERAGE_WEI = str(10 ** 17)
TRIGGER_MM = '35'
PAYOUT_PCT = 80
CHALLENGE = 300
DRY = [0.0, 0.4, 2.6, 1.6, 0.2, 0.0, 1.2]          # sums to 6.0 mm
WET = [12.0, 15.0, 9.0, 0.0, 21.5, 3.0, 0.4]       # sums to 60.9 mm


def iso_day(start, i):
    d = datetime.date.fromisoformat(start)
    return (d + datetime.timedelta(days=i)).isoformat()


def record(window, values):
    return {
        'latitude': -6.221441, 'longitude': 106.856186,
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


def canon(window, values=DRY):
    parsed = record(window, values)
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
        'policy_id': 'policy-1', 'buyer': kw.pop('buyer'),
        'lat': LAT, 'lon': LON,
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
    vm.mock_llm(r'.*', json.dumps({'labels': labels, 'reason': reason,
                                   'citations': citations or []}))


def mock_web_pair(vm, w1_body, w2_body):
    vm.mock_web(r'records/2026-03-09',
                {'status': 200, 'body': w1_body})
    vm.mock_web(r'.*', {'status': 200, 'body': w2_body})


@pytest.fixture
def c(direct_deploy, direct_vm):
    install_transfer_hook(direct_vm)
    return direct_deploy('contracts/rainhedge.py')


@pytest.fixture
def funded(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.deal(direct_vm._to_bytes(direct_vm._contract_address),
                   int(PREMIUM_WEI) * 10)
    direct_vm.value = int(PREMIUM_WEI)
    c.fund_policy('policy-1')
    direct_vm.value = 0
    return c


# ---------------- open_policy validation ----------------

def test_open_then_read_back(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    p = json.loads(c.get_policy('policy-1'))
    assert p['status'] == 'ACTIVE'
    assert p['trigger_mm'] == '35.000000'
    assert len(p['windows']) == 2
    assert p['windows'][0] == [W1[0], W1[1]]
    assert p['balance_wei'] == '0'
    assert p['premium_wei'] == PREMIUM_WEI


def test_open_duplicate_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    with direct_vm.expect_revert('policy_exists'):
        c.open_policy(**policy_json(buyer=direct_alice.as_hex))


def test_open_by_non_owner_is_fine_buyer_is_explicit(c, direct_vm,
                                                     direct_alice,
                                                     direct_bob):
    """The buyer field is explicit — anyone may open cover FOR a buyer;
    only the buyer can fund (proven later)."""
    direct_vm.sender = direct_bob
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    p = json.loads(c.get_policy('policy-1'))
    assert p['buyer'].lower() == direct_alice.as_hex.lower()


@pytest.mark.parametrize('field,value,reason', [
    ('policy_id', 'Bad_Id!', 'invalid_policy_id'),
    ('buyer', '0xdeadbeef', 'invalid_buyer_address'),
    ('lat', '200', 'invalid_lat'),
    ('lon', '-999', 'invalid_lon'),
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
def test_open_validation(c, direct_vm, direct_alice, field, value, reason):
    direct_vm.sender = direct_alice
    args = policy_json(buyer=direct_alice.as_hex)
    args[field] = value
    with direct_vm.expect_revert(reason):
        c.open_policy(**args)


def test_open_wrong_repo_path_reverts(c, direct_vm, direct_alice):
    """A pin outside THIS repo's records/ path (different repo, same
    format) is rejected: pins must commit to the project's own ported
    record set, not an arbitrary paste target."""
    direct_vm.sender = direct_alice
    bad = pin(W1)
    bad['url'] = bad['url'].replace('/' + REPO + '/', '/otherrepo/')
    with direct_vm.expect_revert('invalid_pinned_url'):
        c.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([bad, pin(W2)])))


def test_open_duplicate_pin_window_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('duplicate_pin_window'):
        c.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(W1), pin(W1)])))


def test_open_bad_digest_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('invalid_digest'):
        c.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(W1, digest='z' * 64), pin(W2)])))


def test_open_five_pins_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert('invalid_days_count'):
        c.open_policy(**policy_json(
            buyer=direct_alice.as_hex,
            days_json=json.dumps([pin(w) for w in (W1, W2, W3, W4, W1)])
            [:0] or json.dumps([pin(W1), pin(W2), pin(W3), pin(W4),
                                pin(W1)])))


def test_stats_and_exposure_after_open(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    assert json.loads(c.get_exposure())['total_exposure_wei'] == \
        COVERAGE_WEI
    assert json.loads(c.list_policies()) == ['policy-1']


# ---------------- funding guards ----------------

def test_fund_requires_exact_premium(funded):
    p = json.loads(funded.get_policy('policy-1'))
    assert p['balance_wei'] == PREMIUM_WEI
    assert p['status'] == 'ACTIVE'


def test_fund_wrong_value_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.value = int(PREMIUM_WEI) + 1
    with direct_vm.expect_revert('send exactly the premium'):
        c.fund_policy('policy-1')
    direct_vm.value = 0


def test_fund_by_non_buyer_reverts(c, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    direct_vm.sender = direct_bob
    direct_vm.value = int(PREMIUM_WEI)
    with direct_vm.expect_revert('only_the_buyer_can_fund'):
        c.fund_policy('policy-1')
    direct_vm.value = 0


def test_fund_twice_reverts(funded, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    direct_vm.value = int(PREMIUM_WEI)
    with direct_vm.expect_revert('already_funded'):
        funded.fund_policy('policy-1')
    direct_vm.value = 0


# ---------------- resolution guards ----------------

def test_resolve_before_challenge_reverts(funded, direct_vm):
    with direct_vm.expect_revert('challenge_period_active'):
        funded.resolve_policy('policy-1')


def test_resolve_unfunded_reverts(c, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    c.open_policy(**policy_json(buyer=direct_alice.as_hex))
    warp(direct_vm)
    with direct_vm.expect_revert('not_funded'):
        c.resolve_policy('policy-1')


def test_resolve_unknown_policy(c):
    with pytest.raises(Exception):
        c.resolve_policy('nope-x')


def test_resolve_twice_reverts(funded, direct_vm):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    with direct_vm.expect_revert('not_active'):
        funded.resolve_policy('policy-1')


# ---------------- parametric outcomes ----------------

def test_drought_payout(funded, direct_vm, direct_alice):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['status'] == 'RESOLVED'
    assert p['result']['verdict'] == 'PAYOUT'
    assert p['result']['totals_mm'] == ['6.000000', '6.000000']
    assert p['paid_wei'] == str(int(PREMIUM_WEI) * PAYOUT_PCT // 100)
    assert p['claimable_wei'] == str(int(PREMIUM_WEI)
                                     - int(PREMIUM_WEI) * PAYOUT_PCT // 100)
    assert stats(funded)['payout'] == 1
    # value actually moved: contract balance dropped by the payout amount
    contract_bytes = direct_vm._to_bytes(direct_vm._contract_address)
    assert direct_vm._balances[contract_bytes] == \
        int(PREMIUM_WEI) * 10 - int(p['paid_wei'])


def test_rain_no_payout_refunds_premium(c, direct_vm, direct_alice):
    """Underwrite a WET week (pins over wet bytes), resolve against the
    same wet bytes: totals clear the trigger -> premium refunded."""
    direct_vm.sender = direct_alice
    wet_pins = json.dumps([pin(W1, sha(canon(W1, WET))),
                           pin(W2, sha(canon(W2, WET)))])
    c.open_policy(**policy_json(buyer=direct_alice.as_hex,
                                days_json=wet_pins))
    direct_vm.deal(direct_vm._to_bytes(direct_vm._contract_address),
                   int(PREMIUM_WEI))
    direct_vm.value = int(PREMIUM_WEI)
    c.fund_policy('policy-1')
    direct_vm.value = 0
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1, WET), canon(W2, WET))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['verdict'] == 'NO_PAYOUT'
    assert p['result']['totals_mm'] == ['60.900000', '60.900000']
    assert p['paid_wei'] == '0'
    assert stats(c)['no_payout'] == 1


def test_one_wet_window_blocks_payout(c, direct_vm, direct_alice):
    """Parametric rule is strict: EVERY window must be below trigger.
    Pin 1 underwrites a dry week, pin 2 a wet week; the source serves
    exactly what was pinned; the verdict is NO_PAYOUT."""
    direct_vm.sender = direct_alice
    mixed = json.dumps([pin(W1), pin(W2, sha(canon(W2, WET)))])
    c.open_policy(**policy_json(buyer=direct_alice.as_hex,
                                days_json=mixed))
    direct_vm.deal(direct_vm._to_bytes(direct_vm._contract_address),
                   int(PREMIUM_WEI))
    direct_vm.value = int(PREMIUM_WEI)
    c.fund_policy('policy-1')
    direct_vm.value = 0
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1, DRY), canon(W2, WET))
    c.resolve_policy('policy-1')
    p = json.loads(c.get_policy('policy-1'))
    assert p['result']['totals_mm'] == ['6.000000', '60.900000']
    assert p['result']['verdict'] == 'NO_PAYOUT'


def test_missing_record_inconclusive_fails_closed(funded, direct_vm):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'server error'})
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'
    # the fetched record may legitimately be CONSISTENT; the MISSING one
    # is demoted to UNVERIFIABLE and poisons the evidence basis
    assert p['result']['labels'] == ['CONSISTENT', 'UNVERIFIABLE']
    assert p['result']['totals_mm'] == []
    assert p['claimable_wei'] == PREMIUM_WEI
    assert stats(funded)['inconclusive'] == 1


def test_tampered_record_inconclusive(funded, direct_vm):
    """Fetched bytes that do not match the pin (wrong window content)
    fail closed — even though the data itself looks valid."""
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W3))  # W3 bytes != W2 pin
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_digest_binding_dry_pin_wet_bytes(funded, direct_vm, direct_alice):
    """A pin computed over WET bytes while the source serves DRY bytes:
    digest mismatch -> fail-closed, never a payout. This is the
    underwriting-binding guarantee."""
    buyer = json.loads(funded.get_policy('policy-1'))['buyer']
    direct_vm.sender = direct_alice
    funded.open_policy(**policy_json(
        policy_id='policy-2',
        buyer=buyer,
        days_json=json.dumps([pin(W1),
                              {'url': url(W2),
                               'digest': sha(canon(W2, WET))}])))
    direct_vm.value = int(PREMIUM_WEI)
    funded.fund_policy('policy-2')
    direct_vm.value = 0
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    mock_web_pair(direct_vm, canon(W1), canon(W2, DRY))  # source: DRY
    funded.resolve_policy('policy-2')
    p = json.loads(funded.get_policy('policy-2'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_model_dissent_fails_closed(funded, direct_vm):
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'INCONSISTENT'])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_uncited_label_demoted(funded, direct_vm):
    """CONSISTENT without a citation degrades to UNVERIFIABLE — evidence
    or it did not happen."""
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'CONSISTENT'],
                    citations=[{'source': 0, 'quote': '"2026-03-09"'}])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['result']['labels'] == ['CONSISTENT', 'UNVERIFIABLE']
    assert p['result']['verdict'] == 'INCONCLUSIVE'


def test_bad_citation_dropped(funded, direct_vm):
    """Quotes that are NOT verbatim in the fetched record are dropped;
    a label left uncited by the drop degrades to UNVERIFIABLE."""
    warp(direct_vm)
    mock_llm_labels(direct_vm, ['CONSISTENT', 'CONSISTENT'],
                    citations=[
                        {'source': 0, 'quote': 'not-in-document'},
                        {'source': 0, 'quote': '"2026-03-09"'},
                        {'source': 1, 'quote': '"2026-05-25"'}])
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    quotes = [c['quote'] for c in p['result']['citations']]
    assert 'not-in-document' not in quotes
    assert '"2026-03-09"' in quotes
    assert p['result']['verdict'] == 'PAYOUT'


def test_model_json_garbage_fails_closed(funded, direct_vm):
    warp(direct_vm)
    direct_vm.mock_llm(r'.*', 'not json at all')
    mock_web_pair(direct_vm, canon(W1), canon(W2))
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['result']['verdict'] == 'INCONCLUSIVE'


# ---------------- refund path ----------------

def test_claim_refund_after_inconclusive(funded, direct_vm, direct_alice):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'down'})
    funded.resolve_policy('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['claimable_wei'] == PREMIUM_WEI
    direct_vm.sender = direct_alice
    funded.claim_refund('policy-1')
    p = json.loads(funded.get_policy('policy-1'))
    assert p['claimable_wei'] == '0'
    with direct_vm.expect_revert('nothing_claimable'):
        funded.claim_refund('policy-1')


def test_claim_refund_requires_buyer(funded, direct_vm, direct_bob):
    warp(direct_vm)
    mock_llm_ok(direct_vm)
    direct_vm.mock_web(r'records/2026-03-09',
                       {'status': 200, 'body': canon(W1)})
    direct_vm.mock_web(r'.*', {'status': 500, 'body': 'down'})
    funded.resolve_policy('policy-1')
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('only_the_buyer_can_claim'):
        funded.claim_refund('policy-1')


def test_claim_refund_before_resolve_reverts(funded, direct_vm):
    with direct_vm.expect_revert('not_resolved'):
        funded.claim_refund('policy-1')
