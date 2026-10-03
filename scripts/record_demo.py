#!/usr/bin/env python3
"""RainHedge live demo recording: real policy through the real dApp.

Opens a REAL policy from the UI (burner wallet + faucet), funds it, waits
out the challenge window, resolves from the UI, and captures the PAYOUT
verdict + totals + witness labels. Saves held screenshots for ffmpeg
assembly + a full-speed webm (backup).

Media lives in ~/rainhedge-artifacts (OUTSIDE the repo): the gltest
pytest runner wipes ./artifacts relative to the repo cwd.
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/home/ubuntu/rainhedge-artifacts/demo_shots")
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://faisalnugroho.github.io/rainhedge/"
# contract address read from the deployed frontend (single source of truth)
import re
_html = Path(__file__).resolve().parents[1].joinpath(
    "frontend/index.html").read_text()
_m = re.search(r'const CONTRACT = "(0x[0-9a-fA-F]{40})"', _html)
CONTRACT = _m.group(1) if _m else \
    "0x57806f65a48bEA713500b79E06F6b0D018fcFFcb"
PID = "video-demo-" + time.strftime("%H%M%S")
SHOT = lambda name: str(OUT / (name + ".png"))
LAT, LON = "-6.2", "106.82"


def ts(page, name, hold=3.0):
    page.screenshot(path=SHOT(name))
    (OUT / (name + ".hold")).write_text(str(hold))
    print("shot:", name, flush=True)


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

    # Open tab is default; fill the form
    pg.fill("#pid", PID)
    pg.fill("#buyer", "")
    pg.click("#btnWallet")          # create burner
    pg.wait_for_function(
        "document.getElementById('btnWallet').textContent.includes('0x')",
        timeout=30000)
    ts(pg, "02-wallet", 2.0)
    pg.click("#btnFaucet")
    time.sleep(2)

    # open the policy on-chain (dApp fetches records + builds pins first)
    pg.click("#btnOpen")
    pg.wait_for_function(
        "document.getElementById('stOpen').className.includes('ok')",
        timeout=180000)
    ts(pg, "03-opened", 3.0)

    # fund
    pg.click('[data-pane="paneFund"]')
    pg.fill("#fundPid", PID)
    pg.click("#btnFund")
    pg.wait_for_function(
        "document.getElementById('stFund').className.includes('ok')",
        timeout=180000)
    ts(pg, "04-funded", 3.0)

    # resolve tab — challenge countdown note
    pg.click('[data-pane="paneResolve"]')
    pg.click("#btnRefresh")
    time.sleep(2)
    ts(pg, "05-list", 2.5)

    # wait out the challenge window (300 s on-chain), then resolve via UI
    print("waiting 310s for challenge window...", flush=True)
    time.sleep(310)
    pg.click("#btnRefresh")
    time.sleep(1.5)
    row = pg.locator(".policyitem", has_text=PID).first
    row.locator("button", has_text="Resolve").click()
    pg.wait_for_function(
        "document.getElementById('stResolve').className.includes('ok') && "
        "document.getElementById('stResolve').textContent.includes('PAYOUT')",
        timeout=240000)
    ts(pg, "06-resolving", 2.0)
    time.sleep(1.5)
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
    time.sleep(4)
    ts(pg, "10-explorer", 3.0)
    b.close()
print("OK screenshots in", OUT)
