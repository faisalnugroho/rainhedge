#!/usr/bin/env python3
"""RainHedge live demo recording: real policy through the real dApp.

Chain-authoritative recovery: studionet RPC intermittently 504s, so page
receipts may never arrive even though the tx landed. Every wait is backed
by an on-chain state poll (get_policy via a fresh in-page SDK client);
the DOM is re-synced by reloading the page when the chain says "done".

Media lives in ~/rainhedge-artifacts (OUTSIDE the repo): the gltest
pytest runner wipes ./artifacts relative to the repo cwd.
"""
import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/home/ubuntu/rainhedge-artifacts/demo_shots")
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://faisalnugroho.github.io/rainhedge/"
_html = Path(__file__).resolve().parents[1].joinpath(
    "frontend/index.html").read_text()
_m = re.search(r'const CONTRACT = "(0x[0-9a-fA-F]{40})"', _html)
CONTRACT = _m.group(1) if _m else \
    "0xA0E9fA8a3F9fd44e16C0dBE498A91609f3ea3F88"
PID = "video-demo-" + time.strftime("%H%M%S")
SHOT = lambda name: str(OUT / (name + ".png"))

# JS evaluated IN PAGE: fresh-client chain reads (no wallet needed)
JS_POLICY = (
    "async (pid) => { try {"
    " const S = window.GenLayerSDK;"
    " const c = S.createClient({ chain: S.studionet });"
    " const raw = await c.readContract({ address: '" + CONTRACT + "',"
    "  functionName: 'get_policy', args: [pid] });"
    " return JSON.parse(typeof raw === 'string' ? raw : String(raw));"
    " } catch (e) { return { error: String(e) }; } }"
)


def ts(page, name, hold=3.0):
    page.screenshot(path=SHOT(name))
    (OUT / (name + ".hold")).write_text(str(hold))
    print("shot:", name, flush=True)


def chain_policy(page, pid):
    try:
        return page.evaluate(JS_POLICY, pid)
    except Exception as err:
        return {"error": str(err)}


def wait_chain(page, pid, predicate, attempts, gap, what):
    p = {}
    for i in range(attempts):
        p = chain_policy(page, pid)
        if "error" not in p and predicate(p):
            print(f"[chain] {what}: OK (attempt {i + 1})", flush=True)
            return p
        time.sleep(gap)
    raise RuntimeError(f"chain never showed {what} for {pid}: "
                       + json.dumps(p)[:300])


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 800},
                    record_video_dir=str(OUT / "video"),
                    record_video_size={"width": 1280, "height": 800})
    pg.set_default_timeout(30000)
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_selector(".hero", timeout=30000)
    time.sleep(2)
    ts(pg, "01-home", 3.0)

    # wallet
    pg.fill("#pid", PID)
    pg.click("#btnWallet")
    pg.wait_for_function(
        "document.getElementById('btnWallet').textContent.includes('0x')",
        timeout=30000)
    ts(pg, "02-wallet", 2.0)
    # faucet — retry until the toast confirms, RPC here also flakes
    for f in range(8):
        pg.click("#btnFaucet")
        time.sleep(6)
        toast_txt = pg.evaluate(
            "document.getElementById('toast').textContent")
        if "Faucet sent" in toast_txt:
            print("[faucet] funded", flush=True)
            break
        print(f"[faucet] retry {f + 1}: " + toast_txt[:80], flush=True)
        time.sleep(10)

    # open — studionet RPC intermittently drops ("Failed to fetch"), so
    # retry the WHOLE open until the CHAIN shows ACTIVE; the page
    # receipt/status is advisory only.
    landed = False
    for attempt in range(6):
        if attempt:
            pg.evaluate("document.getElementById('stOpen').textContent=''")
            print(f"[open] retry attempt {attempt + 1}", flush=True)
            time.sleep(20)
        pg.click("#btnOpen")
        for i in range(20):
            cls = pg.evaluate(
                "document.getElementById('stOpen').className")
            if "ok" in cls:
                landed = True
                break
            if "err" in cls:
                pol = chain_policy(pg, PID)
                if pol.get("status") == "ACTIVE":
                    print("[chain] open landed (page missed receipt)",
                          flush=True)
                    landed = True
                break  # retry loop decides
            time.sleep(15)
        if landed:
            break
        pol = chain_policy(pg, PID)
        if pol.get("status") == "ACTIVE":
            print("[chain] open landed (verified post-fail)", flush=True)
            landed = True
            break
    if not landed:
        raise RuntimeError("open never landed: "
                           + json.dumps(chain_policy(pg, PID))[:200])
    ts(pg, "03-opened", 3.0)

    # fund — chain state is the truth
    pg.click('[data-pane="paneFund"]')
    pg.fill("#fundPid", PID)
    pg.click("#btnFund")
    wait_chain(pg, PID,
               lambda q: int(q.get("balance_wei") or "0", 10) > 0,
               24, 15, "funded")
    pg.evaluate("location.reload()")
    pg.wait_for_selector(".hero", timeout=30000)
    time.sleep(2)
    ts(pg, "04-funded", 3.0)

    # resolve tab — list already shows the smoke policies
    pg.click('[data-pane="paneResolve"]')
    pg.click("#btnRefresh")
    time.sleep(2)
    ts(pg, "05-list", 2.5)

    print("waiting 310s for challenge window...", flush=True)
    time.sleep(310)
    pg.click("#btnRefresh")
    time.sleep(1.5)
    row = pg.locator(".policyitem", has_text=PID).first
    row.locator("button", has_text="Resolve").click()

    def resolved_payout(q):
        return (q.get("status") == "RESOLVED"
                and (q.get("result") or {}).get("verdict") == "PAYOUT")
    wait_chain(pg, PID, resolved_payout, 26, 15, "resolved PAYOUT")
    ts(pg, "06-resolving", 2.0)
    pg.evaluate("location.reload()")
    pg.wait_for_selector(".hero", timeout=30000)
    time.sleep(2.5)
    ts(pg, "07-verdict", 5.0)

    # details pane: totals + witness labels + citations
    pg.click('[data-pane="paneView"]')
    pg.fill("#viewPid", PID)
    pg.click("#btnView")
    pg.wait_for_selector("#viewOut .policyitem", timeout=30000)
    ts(pg, "08-details", 4.5)

    # hero gauge now shows the resolved measurement
    pg.click(".logo")
    time.sleep(2.5)
    ts(pg, "09-gauge", 3.5)

    # explorer
    pg.goto("https://explorer-studio.genlayer.com/address/" + CONTRACT,
            wait_until="domcontentloaded")
    time.sleep(5)
    ts(pg, "10-explorer", 3.0)
    b.close()
print("OK screenshots in", OUT)
