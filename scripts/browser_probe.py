#!/usr/bin/env python3
"""One-off probe: can a REAL browser on this computer load PlayARAM
profile pages past Cloudflare?

Plain HTTP fetches (urllib) get a Cloudflare 403 from server addresses,
so the daily updater keeps the Nov 8 snapshot. A real Chromium can run
the JavaScript challenge that blocks simple fetches — this probe checks
whether that is enough from a GitHub Actions runner.

Usage (in the test workflow only — it never touches the leaderboard):
    pip install playwright
    python -m playwright install chromium --with-deps
    python scripts/browser_probe.py

It prints one verdict line per player and a summary, and always exits 0:
    PROBE I3i3oy: LOADED (20 game cards)
    PROBE Vincent Chan: BLOCKED (Cloudflare challenge page)
    PROBE SUMMARY: 5/5 loaded

Rules: no CAPTCHA/Turnstile solving, no login, no clicking anything
except loading the profile page. If a challenge appears, that player
is BLOCKED and the probe moves on. One page load per player, a few
seconds apart — the same gentle pace as the daily updater.
"""

import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYERS_PATH = ROOT / "players.yaml"
PLAYARAM_BASE = "https://playaram.gg"

# Same challenge markers as scripts/update.py.
CHALLENGE_MARKERS = ("Just a moment", "cf-chl",
                     "challenges.cloudflare.com", "cf-turnstile")


def load_players():
    """Minimal YAML reader for the simple players.yaml format
    (mirrored from scripts/update.py — no PyYAML needed)."""
    text = PLAYERS_PATH.read_text()
    players, current = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- name:"):
            if current:
                players.append(current)
            current = {"name": line.split(":", 1)[1].strip().strip('"').strip("'")}
        elif current and ":" in line:
            k, v = line.split(":", 1)
            current[k.strip()] = v.strip().strip('"').strip("'")
    if current:
        players.append(current)
    return players


def playaram_profile_url(riot_id, region):
    """Same URL shape as scripts/update.py: region na1 -> na."""
    short_region = re.sub(r"\d+$", "", (region or "na1").lower()) or "na"
    name, tag = riot_id.rsplit("#", 1)
    return ("{}/en/profile/{}/{}"
            .format(PLAYARAM_BASE, short_region,
                    urllib.parse.quote(f"{name}#{tag}")))


def probe_player(browser, name, riot_id, region):
    """Load one profile in a fresh browser context. Returns a verdict
    string: 'LOADED (N game cards)' or 'BLOCKED (<reason>)'."""
    url = playaram_profile_url(riot_id, region)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"),
    )
    page = context.new_page()
    try:
        try:
            response = page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:  # TimeoutError and friends
            return f"BLOCKED (page did not load: {type(e).__name__})"
        if response is not None and response.status in (401, 403):
            return f"BLOCKED (HTTP {response.status})"
        # The game list is server-rendered, but give the challenge
        # scripts a moment to redirect if one is coming.
        try:
            page.wait_for_selector("text=ARAM: Mayhem", timeout=60000)
        except Exception:
            pass
        html = page.content()
        if any(m in html for m in CHALLENGE_MARKERS):
            return "BLOCKED (Cloudflare challenge page)"
        cards = html.count("ARAM: Mayhem")
        if cards >= 1:
            return f"LOADED ({cards} game cards)"
        title = ""
        try:
            title = page.title()
        except Exception:
            pass
        snippet = re.sub(r"\s+", " ", page.inner_text("body")[:200])
        return f"BLOCKED (no game list; title={title!r} text={snippet!r})"
    finally:
        context.close()


def main():
    from playwright.sync_api import sync_playwright

    players = [p for p in load_players() if p.get("riot_id") and "#" in p["riot_id"]]
    if not players:
        print("PROBE: no players with a full Riot ID in players.yaml.")
        return 0
    loaded = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for i, p in enumerate(players):
                if i:
                    time.sleep(3)  # gentle pace, same as the daily updater
                verdict = probe_player(browser, p["name"], p["riot_id"],
                                       p.get("region", "na1"))
                print(f"PROBE {p['name']}: {verdict}", flush=True)
                if verdict.startswith("LOADED"):
                    loaded += 1
        finally:
            browser.close()
    print(f"PROBE SUMMARY: {loaded}/{len(players)} loaded", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
