#!/usr/bin/env python3
"""
ARAM Mayhem leaderboard updater — last 50 games per player, once a day.

Data source: PlayARAM.gg player profiles (no Riot API key needed — Riot's
public API does not reliably serve ARAM Mayhem, queue 2400 / mode KIWI).

Why this is built this way
---------------------------
The old page got blocked because every refresh hit a live data source.
PlayARAM.gg has no public API, so scraping it on every page load is
also what gets a site blocked. This updater is the opposite:
  * The web page (index.html) makes ZERO calls to Riot or PlayARAM.
    Refreshing it just reloads data/data.json.
  * Only this script talks to PlayARAM, once a day from GitHub Actions
    (12:00 AM CST). It fetches each player's profile page (the first
    20 games are server-rendered in the HTML) and merges the new games
    into a per-player cache, so the last-50 window fills over the first
    few daily runs. Games are deduped by a fingerprint (champion + KDA
    + duration + CS + skillshots dodged), because PlayARAM publishes no
    match IDs.
  * If PlayARAM blocks the request (Cloudflare) or returns no usable
    games, the script does NOT wipe the leaderboard. It keeps the last
    snapshot, records the failure on the page, and tries again at
    12:30 AM. See README.md.
  * Nov 8 evening: GitHub's computers are blocked by Cloudflare too
    (403 on the first request), so server fetching cannot be the
    primary source. The primary source is now the Chrome extension
    (extension/): it runs in Natalie's own browser, on her home
    connection, reads the 5 profiles the way she would, and downloads
    one JSON file. She drops it in data/ as extension-export.json and
    this script imports it with --from-extension, merging into the
    same cache (same fingerprints, same dedupe). The nightly PlayARAM
    fetch above stays as a fallback that fails gracefully.

What PlayARAM's match list shows (collapsed row) — and what it doesn't:
  * Shows: result, relative date ("14h ago"), duration, champion,
    KDA, CS, the 4 Mayhem event stats (hats, event takedowns, snowballs
    hit, skillshots dodged), augment names (best effort), and links to
    all 10 players' profiles (used for stack detection: the 5 players
    on the profile player's team).
  * Does NOT show: per-game damage dealt/taken, per-player turret
    takedowns, or match IDs. (Damage lives only in the expandable
    Details panel, which renders on demand — it is not in the HTML
    the updater fetches, confirmed Nov 8.) So the Output and
    Conversion criteria stay blank for PlayARAM games — a game grade
    is the mean of the criteria available for that game (KDA,
    Teamplay when team totals exist, Death Quality, Augments).
    Missing data is never scored as 0.

Usage:
  python scripts/update.py                        # PlayARAM mode
  python scripts/update.py --from-csv data/manual_games.csv
  python scripts/update.py --from-extension data/extension-export.json
  python scripts/update.py --dry-run              # PlayARAM mode, no writes

Stdlib only. No extra packages to install.
"""

import csv
import html.parser
import http.client
import json
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "data.json"
PLAYERS_PATH = ROOT / "players.yaml"
PLAYARAM_CACHE_DIR = ROOT / "data" / "cache" / "playaram"
CSV_PATH = ROOT / "data" / "manual_games.csv"
EXTENSION_EXPORT_PATH = ROOT / "data" / "extension-export.json"

CST = timezone(timedelta(hours=-6))  # CST, UTC-6 (Nov-Mar)

PLAYARAM_BASE = "https://playaram.gg"
CACHE_KEEP = 100  # keep up to 100 cached games per player; score the newest 50


# ---------------------------------------------------------------- players.yaml
def load_players():
    """Minimal YAML reader for the simple players.yaml format (no PyYAML needed)."""
    text = PLAYERS_PATH.read_text()
    players, current, window = [], {}, 50
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("window_games:"):
            try:
                window = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
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
    return players, window


# ---------------------------------------------------------------- PlayARAM
class PlayARAMBlocked(Exception):
    """PlayARAM answered with a Cloudflare challenge / 403 — automated
    fetching is blocked from this computer. Not fatal: keep the snapshot."""


class PlayARAMFetchError(Exception):
    """Any other fetch problem (404, network down, …)."""


def playaram_region(region):
    """players.yaml region is the platform, e.g. 'na1'; PlayARAM's
    profile URLs use the short region, e.g. 'na'."""
    return re.sub(r"\d+$", "", (region or "na1").lower()) or "na"


def playaram_profile_url(riot_id, region):
    name, tag = riot_id.rsplit("#", 1)
    # PlayARAM lowercases the name in the URL (PikabUwU -> pikabuwu,
    # "Vincent Chan" -> vincent%20chan, # -> %23). These exact URLs
    # were verified against the ones Natalie pasted from her browser.
    return ("{}/en/profile/{}/{}"
            .format(PLAYARAM_BASE, playaram_region(region),
                    urllib.parse.quote(f"{name.lower()}#{tag}")))


def _is_cloudflare_challenge(html):
    return ("Just a moment" in html or "cf-chl" in html
            or "challenges.cloudflare.com" in html or "cf-turnstile" in html)


def fetch_profile_html(url):
    """One GET with browser-like headers. Raises PlayARAMBlocked on a
    Cloudflare challenge (403 or a challenge page served with 200)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;"
                   "q=0.9,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            pass
        if e.code in (401, 403) or _is_cloudflare_challenge(body):
            raise PlayARAMBlocked(
                f"PlayARAM returned {e.code} (Cloudflare challenge) — "
                "automated fetching is blocked from this computer.")
        if e.code == 404:
            raise PlayARAMFetchError(
                "PlayARAM profile not found (404) — check the Riot ID in players.yaml.")
        raise PlayARAMFetchError(f"PlayARAM returned HTTP {e.code}.")
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        # Cloudflare sometimes drops the connection instead of answering
        # 403 (RemoteDisconnected). That is a fetch failure, not a crash:
        # the caller keeps the cached games for this player.
        raise PlayARAMFetchError(
            f"Could not reach playaram.gg ({type(e).__name__}: {e}) — "
            "the request was refused or the connection was dropped.")
    if _is_cloudflare_challenge(html):
        raise PlayARAMBlocked(
            "PlayARAM returned a Cloudflare challenge page (HTTP 200) — "
            "automated fetching is blocked from this computer.")
    return html


class _CardBits(html.parser.HTMLParser):
    """Collects one game card's visible text (in order), img info
    (src/alt/title) and profile hrefs, from a raw HTML slice."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts = []
        self.imgs = []   # (src, alt, title)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "img":
            self.imgs.append((d.get("src", ""), d.get("alt", ""),
                              d.get("title", "")))
        if tag == "a" and d.get("href"):
            self.hrefs.append(d["href"])

    def handle_data(self, data):
        t = data.strip()
        if t:
            self.texts.append(t)


def _relative_to_date(text, now):
    """'14h ago' / '1d ago' / 'just now' -> a date (CST). Returns None
    when the text has no relative time at all."""
    if "just now" in text:
        return now.date()
    m = re.search(r"(\d+)\s*(min|h|d|w)\s*ago", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"min": timedelta(minutes=n), "h": timedelta(hours=n),
             "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
    return (now - delta).date()


def parse_profile_games(html, riot_id, now):
    """Parse the (up to) 20 server-rendered game cards on a PlayARAM
    profile page into game rows.

    Observed layout per card (verified against the live profile text):
      'ARAM: Mayhem' Victory|Defeat '14h ago' '26m 57s'
      champion portrait (alt = champion name) + level
      KDA as 10/20/25, then 5 numbers: CS, hats, event takedowns,
      snowballs hit, skillshots dodged   <-- order assumption, see below
      badges (ACE, MVP, …) — ignored
    Augment names are taken from img alt/title attributes in the card,
    excluding the champion portrait and item icons; if the markup does
    not expose them, augments stay [] and the Augments component scores
    a neutral 50. Stack comes from the 10 profile links in the card:
    the 5 links in the profile player's half are their team.
    Returns (games, diagnostics dict). Games are newest-first.
    """
    diag = {"segments": 0, "parsed": 0, "skipped": 0,
            "no_kda": 0, "no_numbers": 0, "no_champion": 0,
            "with_augments": 0, "with_participants": 0}
    # One card per 'ARAM: Mayhem' header. The page <title> says
    # 'ARAM Mayhem' (no colon), so it does not split there.
    segments = re.split(r"ARAM:\s*Mayhem", html)
    games = []
    me_norm = _norm_champ(riot_id.replace("#", ""))
    for seg in segments[1:]:
        diag["segments"] += 1
        bits = _CardBits()
        try:
            bits.feed(seg)
        except Exception:
            diag["skipped"] += 1
            continue
        text = " ".join(bits.texts)
        m_win = re.search(r"\b(Victory|Defeat)\b", text)
        m_dur = re.search(r"(\d+)\s*m\s*(\d+)\s*s\b", text)
        m_kda = re.search(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", text)
        # Champion: the /media/champion/<id>.png portrait; alt is the name.
        champ, champ_key = None, None
        for src, alt, _title in bits.imgs:
            m_img = re.search(r"/media/champion/(\d+)\.png", src)
            if m_img:
                champ_key = m_img.group(1)
                champ = alt.strip() or None
                break
        if not champ and champ_key:
            champ = CHAMPION_BY_KEY.get(champ_key)
        if not m_kda:
            diag["no_kda"] += 1
            diag["skipped"] += 1
            continue
        if not champ:
            diag["no_champion"] += 1
            diag["skipped"] += 1
            continue
        kills, deaths, assists = (int(m_kda.group(i)) for i in (1, 2, 3))
        # The 5 numbers after the KDA: CS, hats, event takedowns,
        # snowballs hit, skillshots dodged — in that display order.
        # VERIFIED Nov 8 by live-DOM inspection: the four event pills
        # carry the labels "Event hats", "Event takedowns",
        # "Snowballs hit", "Skillshots dodged", in that order.
        after = text[m_kda.end():]
        nums = [int(n) for n in re.findall(r"\b\d+\b", after)][:5]
        if len(nums) < 5:
            diag["no_numbers"] += 1
            diag["skipped"] += 1
            continue
        cs, _hats, _takedowns, _snowballs, dodged = nums
        mins = 0.0
        if m_dur:
            mins = int(m_dur.group(1)) + int(m_dur.group(2)) / 60.0
        if mins < 5:  # remake under 5 minutes
            diag["skipped"] += 1
            continue
        date = _relative_to_date(text, now)
        date_s = date.isoformat() if date else now.date().isoformat()
        # Augments: img alt/title, excluding the champion portrait,
        # item icons, and summoner spell icons (Mark / Flash). The
        # class icon (e.g. alt "HEAVY") is kept — the site's own
        # Augments tab names class + 4 augments per player. The 6th
        # framed slot has no name and is skipped. Verified Nov 8 by
        # live-DOM inspection: augment icons live under
        # /media/game-asset/.../augments/icons/ with alt = the name.
        augments = []
        for src, alt, title in bits.imgs:
            low = src.lower()
            if ("champion" in low or "item" in low or "spell" in low
                    or "summoner" in low):
                continue
            name = (alt or title or "").strip()
            if name and name not in augments:
                augments.append(name)
        if augments:
            diag["with_augments"] += 1
        # Participants: /en/profile/<region>/<RiotID> links, in DOM
        # order — two groups of 5, one per team.
        participants = []
        for href in bits.hrefs:
            m_p = re.match(r"/en/profile/[a-z0-9]+/([^\"'/?#]+)", href)
            if m_p:
                rid = urllib.parse.unquote(m_p.group(1))
                if rid not in participants:
                    participants.append(rid)
        teammates = []
        if len(participants) >= 10:
            diag["with_participants"] += 1
            teams = [participants[:5], participants[5:10]]
            for team in teams:
                if any(_norm_champ(r.replace("#", "")) == me_norm for r in team):
                    teammates = [r for r in team
                                 if _norm_champ(r.replace("#", "")) != me_norm]
                    break
        fingerprint = (f"{champ}|{kills}/{deaths}/{assists}|{mins:.1f}|"
                       f"{cs}|{dodged}|{date_s}")
        games.append({
            "match_id": fingerprint,
            "date": date_s,
            "champion": champ,
            "archetype": "Damage",  # filled in by caller
            "win": (m_win.group(1) == "Victory") if m_win else False,
            "kills": kills, "deaths": deaths, "assists": assists,
            "damage_to_champions": None,  # not on PlayARAM's match list
            "damage_taken": None,          # not on PlayARAM's match list
            "game_minutes": round(mins, 2),
            "dmg_share": None, "kp": None, "structure_share": None,
            "augments": augments,
            "skillshots_dodged_per_min": (
                round(dodged / mins, 2) if mins else None),
            # Stack is counted by the caller (it knows the group):
            # teammates here are Riot IDs of the other 4 on the team.
            "stack_size": None, "teammates": teammates,
        })
        diag["parsed"] += 1
    return games, diag


def _cache_path(name):
    return PLAYARAM_CACHE_DIR / f"{_norm_champ(name)}.json"


def load_playaram_cache(name):
    p = _cache_path(name)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return []
    return []


def merge_playaram_cache(name, new_games):
    """Merge freshly parsed games into the player's cache, deduped by
    fingerprint. Newest games get the highest seq numbers; the cache
    is capped at CACHE_KEEP. Returns (window games newest-first, n_new)."""
    cached = load_playaram_cache(name)
    seen = {g.get("match_id") for g in cached}
    max_seq = max((g.get("seq", 0) for g in cached), default=0)
    added = 0
    for g in reversed(new_games):  # oldest first, so newest gets top seq
        if g["match_id"] in seen:
            continue
        max_seq += 1
        g["seq"] = max_seq
        cached.append(g)
        seen.add(g["match_id"])
        added += 1
    cached.sort(key=lambda g: g.get("seq", 0), reverse=True)
    cached = cached[:CACHE_KEEP]
    PLAYARAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(name).write_text(json.dumps(cached, indent=2))
    return cached, added


# ---------------------------------------------------------------- champion archetype
DDRAGON_VERSION = "16.22.1"  # pinned Data Dragon version (same one champion.json comes from)
# Normalized champion name ("aurelionsol", "kaisa", "wukong") -> portrait URL.
# Normalizing handles both Riot IDs ("AurelionSol", "MonkeyKing") and display
# names ("Aurelion Sol", "Wukong", "Kai'Sa") from a manual CSV.
CHAMPION_IMAGES = {}
# Data Dragon numeric key ("48") -> champion ID ("Trundle"), for
# PlayARAM's /media/champion/<id>.png portraits.
CHAMPION_BY_KEY = {}
# Normalized name (ID or display name, e.g. "wukong", "monkeyking") ->
# archetype, so PlayARAM names resolve whichever form the site uses.
ARCHETYPE_BY_NORM = {}


def archetype_for(name):
    """Damage / Frontline / Support for a champion name in any form
    (Riot ID, display name, PlayARAM alt text), or 'Damage' fallback."""
    if not name:
        return "Damage"
    return (ARCHETYPE_BY_NORM.get(_norm_champ(name))
            or ARCHETYPE_BY_NORM.get(_norm_champ(name.replace("'", "")))
            or "Damage")


def _norm_champ(name):
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def champion_image(name):
    """Official Data Dragon square portrait URL for a champion, or None."""
    return CHAMPION_IMAGES.get(_norm_champ(name))


def champion_archetypes():
    """Damage / Frontline / Support from Data Dragon tags (no key needed)."""
    try:
        url = "https://ddragon.leagueoflegends.com/cdn/16.22.1/data/en_US/champion.json"
        with urllib.request.urlopen(url, timeout=30) as resp:
            champs = json.loads(resp.read().decode())["data"]
        out = {}
        for champ_id, c in champs.items():
            tags = c.get("tags", [])
            if "Support" in tags:
                arch = "Support"
            elif "Tank" in tags:
                arch = "Frontline"
            elif "Fighter" in tags:
                arch = "Frontline"
            else:
                arch = "Damage"
            out[champ_id] = arch
            CHAMPION_BY_KEY[str(c.get("key", ""))] = champ_id
            for key in {champ_id, c.get("name", "")}:
                if key:
                    ARCHETYPE_BY_NORM[_norm_champ(key)] = arch
            # Portrait: Data Dragon square image, keyed by both the Riot ID
            # ("MonkeyKing") and the display name ("Wukong"), normalized.
            img = (c.get("image") or {}).get("full") or f"{champ_id}.png"
            url = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/champion/{img}"
            for key in {champ_id, c.get("name", "")}:
                if key:
                    CHAMPION_IMAGES[_norm_champ(key)] = url
        return out
    except Exception as e:
        print(f"  Data Dragon champion list unavailable ({e}) — using Damage for all.", flush=True)
        return {}


# ---------------------------------------------------------------- scoring
def pct_rank(values, x):
    """Percentile 0-100 of x within values (higher is better)."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return 100.0 * (below + 0.5 * equal) / len(values)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def annotate_stack(all_games):
    """Count how many of the group were in each match.

    Match IDs are shared across players when they queue together, so the
    number of group members in a match is the stack size for that game.
    It counts only group members whose game is also in this 50-game
    window — a teammate's game outside their own last-50 window won't
    be counted, so a 5-stack can read as a 4-stack near the window edge.
    Games that already carry a stack_size (PlayARAM rows, from the
    participant links) and games with no match_id are left alone.
    """
    present = {}
    for name, games in all_games.items():
        for g in games:
            if g.get("match_id"):
                present.setdefault(g["match_id"], set()).add(name)
    for name, games in all_games.items():
        for g in games:
            if g.get("stack_size") is not None:
                continue
            if not g.get("match_id"):
                g["stack_size"] = 1
                g["teammates"] = []
                continue
            mates = present.get(g["match_id"], {name})
            g["stack_size"] = len(mates)
            g["teammates"] = sorted(m for m in mates if m != name)


def stack_splits(all_games):
    """Win rate + mean grade by stack size, across all player-games."""
    buckets = [("Solo", 1, 1), ("2\u20133 of the group", 2, 3),
               ("4 of the group", 4, 4), ("Full stack (5)", 5, 5)]
    rows_all = [g for games in all_games.values() for g in games]
    out = []
    for label, lo, hi in buckets:
        rows = [g for g in rows_all if lo <= g.get("stack_size", 1) <= hi]
        if not rows:
            continue
        wins = sum(1 for g in rows if g["win"])
        out.append({"label": label, "player_games": len(rows), "wins": wins,
                    "win_rate_pct": round(100.0 * wins / len(rows), 1),
                    "grade": round(statistics.mean(g["grade"] for g in rows), 1)})
    return out


def score_players(all_games, archetypes):
    """
    all_games: {player_name: [game, ...]} where game has the fields in
    parse_profile_games() / rows_from_csv(). Returns updated player dicts.
    Fair ranking, by design:
    * Role first: every component is a percentile WITHIN the player's role
      archetype (Damage / Frontline / Support), so a tank is never judged
      on a carry's kills or damage, and a support is never judged on damage.
    * Champion second: each component blends 70% archetype percentile +
      30% same-champion percentile (only when the group has 3+ games on
      that champion). Playing a champion well *for that champion* counts.
    * Whole performance: a game grade is the mean of the criteria
      available for that game, so KDA is 1 of the graded criteria,
      damage is only part of Output, and win rate is only 15%
      of the final score. No single stat decides the rank.
      PlayARAM's match list has no damage or turret data, so for
      PlayARAM games the grade blends KDA, Teamplay (when team totals
      exist), Death Quality and Augments; Output and Conversion join
      in only when the source provides damage/structure data (a manual
      CSV). Mechanics (skillshots dodged) is shown, not blended.
      A missing field is skipped, never scored as 0.
    Performance Score = 55% mean + 20% median + 10% p25 + 15% win rate.
    MMR-style = 800 + Score x 14.
    Also returns per-player evidence: role split, champion focus, and a
    'why this rank' paragraph built from the numbers.
    """
    # Precompute derived per-minute fields for EVERY game first, so the
    # percentile baselines below can read them on games not yet graded.
    # Missing damage stays None — it is skipped later, never scored as 0.
    for games in all_games.values():
        for g in games:
            mins = max(g["game_minutes"], 1)
            dmg = g.get("damage_to_champions")
            taken = g.get("damage_taken")
            g["dmg_per_min"] = (dmg / mins) if dmg is not None else None
            g["taken_per_min"] = (taken / mins) if taken is not None else None
            g["assists_per_min"] = g["assists"] / mins
            g["kda"] = (g["kills"] + g["assists"]) / max(g["deaths"], 1)
            g["dmg_share"] = g.get("dmg_share")
            g["kp"] = g.get("kp")
            g["structure_share"] = g.get("structure_share")

    # Group games by archetype for percentile baselines.
    by_arch = {}
    for games in all_games.values():
        for g in games:
            by_arch.setdefault(g["archetype"], []).append(g)

    # Augment group win rate, for the Augments component.
    aug_wins, aug_games = {}, {}
    for games in all_games.values():
        for g in games:
            for a in g.get("augments", []):
                aug_games[a] = aug_games.get(a, 0) + 1
                if g["win"]:
                    aug_wins[a] = aug_wins.get(a, 0) + 1

    # Group games by champion too, for the champion adjustment.
    by_champ = {}
    for games in all_games.values():
        for g in games:
            by_champ.setdefault(g["champion"], []).append(g)

    def blended(arch, champ, key, value):
        """70% percentile within role archetype + 30% percentile within
        the same champion (only when the group has 3+ games on it).
        Returns None when the value is missing — a missing field is
        skipped, never scored as 0."""
        if value is None:
            return None
        arch_vals = [g[key] for g in by_arch.get(arch, [])
                     if g.get(key) is not None]
        if not arch_vals:
            return None
        arch_pct = pct_rank(arch_vals, value)
        champ_games = [g for g in by_champ.get(champ, [])
                       if g.get(key) is not None]
        if len(champ_games) >= 3:
            champ_pct = pct_rank([g[key] for g in champ_games], value)
            return 0.7 * arch_pct + 0.3 * champ_pct
        return arch_pct

    results = {}
    for name, games in all_games.items():
        if not games:
            results[name] = None
            continue
        for g in games:
            arch = g["archetype"]
            mins = max(g["game_minutes"], 1)
            dmg = g.get("damage_to_champions")
            taken = g.get("damage_taken")
            g["dmg_per_min"] = (dmg / mins) if dmg is not None else None
            g["taken_per_min"] = (taken / mins) if taken is not None else None
            g["assists_per_min"] = g["assists"] / mins
            g["kda"] = (g["kills"] + g["assists"]) / max(g["deaths"], 1)
            # Team totals are filled in by the caller when available;
            # None stays None (missing, not zero).
            g["dmg_share"] = g.get("dmg_share")
            g["kp"] = g.get("kp")
            g["structure_share"] = g.get("structure_share")

            out_parts = [blended(arch, g["champion"], "dmg_per_min", g["dmg_per_min"]),
                         blended(arch, g["champion"], "dmg_share", g["dmg_share"])]
            out_parts = [p for p in out_parts if p is not None]
            output = sum(out_parts) / len(out_parts) if out_parts else None
            kda = blended(arch, g["champion"], "kda", g["kda"])
            teamplay = blended(arch, g["champion"], "kp", g["kp"])
            death_q = 100 - blended(arch, g["champion"], "deaths", g["deaths"])
            conversion = blended(arch, g["champion"], "structure_share", g["structure_share"])
            if g.get("augments"):
                rates = [aug_wins.get(a, 0) / aug_games[a] for a in g["augments"] if aug_games.get(a, 0) >= 3]
                aug = (sum(rates) / len(rates) * 100) if rates else 50.0
                # Rescale augment win-rate (~35-65%) onto 0-100 for comparability.
                aug = max(0.0, min(100.0, (aug - 35) / 30 * 100))
            else:
                aug = 50.0
            parts = [p for p in [output, kda, teamplay, death_q, conversion, aug]
                     if p is not None]
            g["grade"] = sum(parts) / len(parts) if parts else 50.0
            g["subscores"] = {
                "output": round(output, 1) if output is not None else None,
                "kda_efficiency": round(kda, 1) if kda is not None else None,
                "teamplay": round(teamplay, 1) if teamplay is not None else None,
                "death_quality": round(death_q, 1) if death_q is not None else None,
                "conversion": round(conversion, 1) if conversion is not None else None,
                "augments": round(aug, 1),
                "mechanics": g.get("skillshots_dodged_per_min"),
            }

        grades = sorted(g["grade"] for g in games)
        wins = sum(1 for g in games if g["win"])
        win_rate = 100.0 * wins / len(games)
        mean = statistics.mean(grades)
        score = (0.55 * mean + 0.20 * statistics.median(grades)
                 + 0.10 * percentile(grades, 25) + 0.15 * win_rate)
        results[name] = {
            "score": round(score, 1),
            "mmr_style": int(round(800 + score * 14)),
            "wins": wins, "losses": len(games) - wins, "win_rate": round(win_rate, 1),
            "kda": round(sum((g["kills"] + g["assists"]) for g in games)
                         / max(sum(g["deaths"] for g in games), 1), 2),
            "damage_per_min": (
                round(statistics.mean(g["dmg_per_min"] for g in games
                                      if g.get("dmg_per_min") is not None))
                if any(g.get("dmg_per_min") is not None for g in games) else None),
            "subscores": {k: round(statistics.mean(
                g["subscores"][k] for g in games if g["subscores"][k] is not None), 1)
                if any(g["subscores"][k] is not None for g in games) else None
                for k in ["output", "kda_efficiency", "teamplay", "death_quality",
                          "conversion", "augments", "mechanics"]},
            "skillshots_dodged_per_min": (
                round(statistics.mean(g["skillshots_dodged_per_min"] for g in games
                                      if g.get("skillshots_dodged_per_min") is not None), 2)
                if any(g.get("skillshots_dodged_per_min") is not None for g in games) else None),
            "games": games,
        }

    # --- Evidence: role split, champion focus, why-this-rank ---
    sub_keys = ["output", "kda_efficiency", "teamplay", "death_quality",
                "conversion", "augments", "mechanics"]
    group_avg = {}
    for k in sub_keys:
        vals = [r["subscores"][k] for r in results.values()
                if r and r["subscores"].get(k) is not None]
        group_avg[k] = round(statistics.mean(vals), 1) if vals else None
    ranked = sorted([(n, r) for n, r in results.items() if r],
                    key=lambda nr: nr[1]["score"], reverse=True)
    for rank, (name, r) in enumerate(ranked, 1):
        games = all_games[name]
        mean_grade = statistics.mean(g["grade"] for g in games)
        role_split = {}
        for arch in sorted({g["archetype"] for g in games}):
            ag = [g for g in games if g["archetype"] == arch]
            role_split[arch] = {
                "games": len(ag),
                "mean_grade": round(statistics.mean(g["grade"] for g in ag), 1),
                "delta_vs_overall": round(statistics.mean(g["grade"] for g in ag) - mean_grade, 1),
            }
        champ_rows = []
        for champ in sorted({g["champion"] for g in games}):
            cg = [g for g in games if g["champion"] == champ]
            if len(cg) >= 3:
                cg_mean = statistics.mean(g["grade"] for g in cg)
                cg_wins = sum(1 for g in cg if g["win"])
                cg_delta = round(cg_mean - mean_grade, 1)
                direction = "above" if cg_delta >= 0 else "below"
                champ_rows.append({
                    "champion": champ, "image": champion_image(champ),
                    "games": len(cg),
                    "wins": cg_wins, "losses": len(cg) - cg_wins,
                    "win_rate": round(100.0 * cg_wins / len(cg), 1),
                    "mean_grade": round(cg_mean, 1),
                    "delta_vs_overall": cg_delta,
                    "why": (f"Grades {abs(cg_delta)} points {direction} this player's own "
                            f"average ({round(mean_grade, 1)}) over {len(cg)} games, "
                            f"going {cg_wins}-{len(cg) - cg_wins} on this champion."),
                })
        take = [c for c in sorted(champ_rows, key=lambda c: c["delta_vs_overall"], reverse=True)
                if c["delta_vs_overall"] >= 4]
        pas = [c for c in sorted(champ_rows, key=lambda c: c["delta_vs_overall"])
               if c["delta_vs_overall"] <= -4]
        r["role_split"] = role_split
        r["champion_focus"] = {"take_when_offered": take, "pass_or_swap": pas}
        # Top 3 / worst 3 champions in this 50-game window (3+ games each),
        # ranked by grade vs the player's own average — hard facts, no opinion.
        by_delta_desc = sorted(champ_rows, key=lambda c: c["delta_vs_overall"], reverse=True)
        r["champion_top3"] = by_delta_desc[:3]
        r["champion_worst3"] = sorted(champ_rows, key=lambda c: c["delta_vs_overall"])[:3]

        # --- Recent 20: how to improve, from the freshest 20 games only ---
        # Everything here is computed strictly inside the player's most
        # recent 20 games: no comparison to the other 30 games in the
        # window, and no snapshot numbers. Pros/cons/tips are filled in
        # the second pass below, against the group's recent-20 averages.
        newest = sorted(games, key=lambda g: g.get("date", ""), reverse=True)
        recent = newest[:20]
        r_recent = {}
        if recent:
            r_grades = sorted(g["grade"] for g in recent)
            r_wins = sum(1 for g in recent if g["win"])
            r_wr = 100.0 * r_wins / len(recent)
            r_mean = statistics.mean(r_grades)
            r_score20 = (0.55 * r_mean + 0.20 * statistics.median(r_grades)
                         + 0.10 * percentile(r_grades, 25) + 0.15 * r_wr)
            sub_recent = {}
            for k in sub_keys:
                vals = [g["subscores"][k] for g in recent
                        if g["subscores"].get(k) is not None]
                sub_recent[k] = round(statistics.mean(vals), 1) if vals else None
            # Stacked (2+ of the group) vs solo, inside these same 20 games.
            def _split(gs):
                if not gs:
                    return None
                w = sum(1 for g in gs if g["win"])
                return {"games": len(gs), "wins": w, "losses": len(gs) - w,
                        "win_rate": round(100.0 * w / len(gs), 1),
                        "mean_grade": round(statistics.mean(g["grade"] for g in gs), 1)}
            stacked_20 = _split([g for g in recent if g.get("stack_size", 1) >= 2])
            solo_20 = _split([g for g in recent if g.get("stack_size", 1) == 1])
            team_line = None
            if stacked_20 and solo_20:
                d_grade = round(stacked_20["mean_grade"] - solo_20["mean_grade"], 1)
                d_wr = round(stacked_20["win_rate"] - solo_20["win_rate"], 1)
                s_txt = (f"{stacked_20['wins']}-{stacked_20['losses']} "
                         f"({stacked_20['win_rate']}%, grade {stacked_20['mean_grade']})")
                o_txt = (f"{solo_20['wins']}-{solo_20['losses']} "
                         f"({solo_20['win_rate']}%, grade {solo_20['mean_grade']})")
                # Grade and win rate can point opposite ways (e.g. grading
                # higher together but winning less) — only claim "helps" or
                # "dragging" when both agree; otherwise say mixed.
                grade_up, grade_down = d_grade >= 3, d_grade <= -3
                wr_up, wr_down = d_wr >= 10, d_wr <= -10
                if (grade_up or wr_up) and not (grade_down or wr_down):
                    team_line = (f"Playing together helps you: with 2+ of the group in the last 20 you went "
                                 f"{s_txt} vs solo {o_txt}.")
                elif (grade_down or wr_down) and not (grade_up or wr_up):
                    team_line = (f"Playing together is dragging you down lately: with 2+ of the group in the last 20 you went "
                                 f"{s_txt} vs solo {o_txt}. Check role balance when you stack — someone may be off-role.")
                elif grade_up or grade_down or wr_up or wr_down:
                    team_line = (f"Mixed picture together: with 2+ of the group in the last 20 you went "
                                 f"{s_txt} vs solo {o_txt} — your grades are {d_grade:+.1f} points "
                                 f"{'higher' if d_grade >= 0 else 'lower'} together, but your win rate is "
                                 f"{d_wr:+.1f}% {'higher' if d_wr >= 0 else 'lower'}.")
                else:
                    team_line = (f"With 2+ of the group in the last 20: {s_txt} vs solo {o_txt} — about even.")
            elif stacked_20:
                team_line = (f"All of your last 20 were with 2+ of the group: "
                             f"{stacked_20['wins']}-{stacked_20['losses']} "
                             f"({stacked_20['win_rate']}%, grade {stacked_20['mean_grade']}). "
                             f"No solo games to compare against.")
            elif solo_20:
                team_line = (f"All of your last 20 were solo: "
                             f"{solo_20['wins']}-{solo_20['losses']} "
                             f"({solo_20['win_rate']}%, grade {solo_20['mean_grade']}). "
                             f"No games with the group to compare against.")
            r_recent = {
                "games": len(recent), "wins": r_wins, "losses": len(recent) - r_wins,
                "win_rate": round(r_wr, 1), "mean_grade": round(r_mean, 1),
                "score_20": round(r_score20, 1),
                "subscores": sub_recent, "pros": [], "cons": [], "tips": [],
                "stacked_20": stacked_20, "solo_20": solo_20,
                "team_line": team_line,
            }
        r["recent_20"] = r_recent
        deltas = {k: (r["subscores"][k] - group_avg[k])
                  for k in sub_keys
                  if r["subscores"].get(k) is not None and group_avg.get(k) is not None}
        best = max(deltas, key=deltas.get) if deltas else None
        worst = min(deltas, key=deltas.get) if deltas else None
        best_txt = (f"Strongest vs the group: {best} "
                    f"({r['subscores'][best]} vs group avg {group_avg[best]}, "
                    f"{deltas[best]:+.1f}). " if best else "")
        # If every delta is tied (e.g. all ~0), best and worst are the same —
        # don't print the same criterion as both strongest and weakest.
        if worst == best:
            worst = None
        worst_txt = (f"Weakest vs the group: {worst} "
                     f"({r['subscores'][worst]} vs group avg {group_avg[worst]}, "
                     f"{deltas[worst]:+.1f}). " if worst else "")
        role_txt = "; ".join(
            f"{a} {v['mean_grade']} ({v['games']} games, {v['delta_vs_overall']:+.1f} vs own avg)"
            for a, v in role_split.items())
        r["why_rank"] = (
            f"Ranked {rank} of {len(ranked)} at {r['score']} (MMR-style {r['mmr_style']}, "
            f"{r['wins']}-{r['losses']}, {r['win_rate']}% win rate). "
            f"{best_txt}{worst_txt}"
            f"By role: {role_txt}. "
            f"Win rate is only 15% of the score and no single stat decides "
            f"the rank — each game grade blends every criterion the data "
            f"source provides for that game (from PlayARAM: KDA, teamplay, "
            f"death quality and augments; damage-based output and "
            f"conversion only when damage data exists), graded within role "
            f"and adjusted for champion — not from one stat.")

    # --- Recent-20 pros/cons/tips: within the 20 games only ---
    # Each player's recent-20 subscores are compared with the GROUP's
    # recent-20 averages (same 20-game window, same criteria) — never
    # with the player's own 50-game numbers or the older 30 games.
    label = {"output": "Output", "kda_efficiency": "KDA efficiency",
             "teamplay": "Teamplay", "death_quality": "Death quality",
             "conversion": "Conversion", "augments": "Augments",
             "mechanics": "Mechanics"}
    tip_for = {"output": "focus on damage output and positioning to deal more damage",
               "kda_efficiency": "trade less — fewer deaths for the kills you get",
               "teamplay": "join more fights to raise kill participation",
               "death_quality": "die less, and later in the game",
               "conversion": "turn won fights into turrets",
               "augments": "rethink augment picks — the ones taken lately are underperforming",
               "mechanics": "dodge more skillshots"}
    group_recent_avg = {}
    for k in sub_keys:
        vals = [r["recent_20"]["subscores"][k] for r in results.values()
                if r and r.get("recent_20") and r["recent_20"]["subscores"].get(k) is not None]
        group_recent_avg[k] = round(statistics.mean(vals), 1) if vals else None
    for name, r in results.items():
        if not r or not r.get("recent_20"):
            continue
        rr = r["recent_20"]
        for k in sub_keys:
            mine = rr["subscores"].get(k)
            avg = group_recent_avg.get(k)
            if mine is None or avg is None:
                continue
            diff = round(mine - avg, 1)
            if diff >= 5:
                rr["pros"].append(f"{label[k]} is a strength in the last 20: {mine} vs the group recent-20 avg {avg} ({diff:+.1f}).")
            elif diff <= -5:
                rr["cons"].append(f"{label[k]} is slipping in the last 20: {mine} vs the group recent-20 avg {avg} ({diff:+.1f}).")
                rr["tips"].append(f"Work on {label[k]}: {tip_for[k]}.")
    return results


def public_game(g):
    return {
        "match_id": g["match_id"], "date": g["date"], "champion": g["champion"],
        "win": g["win"], "kills": g["kills"], "deaths": g["deaths"],
        "assists": g["assists"], "damage_to_champions": g["damage_to_champions"],
        "damage_taken": g["damage_taken"], "augments": g.get("augments", []),
        "game_minutes": round(g["game_minutes"], 1),
        "grade": round(g["grade"], 1),
        "stack_size": g.get("stack_size", 1),
        "teammates": g.get("teammates", []),
    }


# ---------------------------------------------------------------- CSV rows
def rows_from_csv():
    if not CSV_PATH.exists():
        return {}
    out = {}
    with CSV_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("player") or not row.get("champion"):
                continue
            try:
                mins = float(row.get("game_minutes") or 0) or 1
                dodges = row.get("skillshots_dodged_per_min")
                # A damage value of 0 means the column was left blank —
                # a real Mayhem game never deals 0 damage. Keep it None
                # so the missing field is skipped, not scored as 0.
                dmg = int(row.get("damage_to_champions") or 0) or None
                taken = int(row.get("damage_taken") or 0) or None
                out.setdefault(row["player"], []).append({
                    "match_id": row.get("match_id") or "",
                    "date": row.get("date") or "",
                    "champion": row["champion"],
                    "archetype": "Damage",
                    "win": str(row.get("win", "")).strip().lower() in ("1", "true", "win", "w"),
                    "kills": int(row.get("kills") or 0),
                    "deaths": int(row.get("deaths") or 0),
                    "assists": int(row.get("assists") or 0),
                    "damage_to_champions": dmg,
                    "damage_taken": taken,
                    "game_minutes": mins,
                    # No team totals in a hand-made CSV — None, not 0,
                    # so the missing fields are skipped, not scored as 0.
                    "dmg_share": None, "kp": None, "structure_share": None,
                    "augments": [a.strip() for a in (row.get("augments") or "").split(";") if a.strip()],
                    "skillshots_dodged_per_min": float(dodges) if dodges else None,
                })
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------- extension export
def rows_from_extension(path, players):
    """Read a browser-extension export into {display_name: [game, ...]}
    in the same shape parse_profile_games() returns, so the existing
    cache merge + scoring just work.

    Export schema (see extension/): {"exported_at", "source":
    "extension", "players": [{"riot_id", "display_name", "games":
    [{champion, win, date, duration_minutes, kills, deaths, assists,
    cs, hats, event_takedowns, snowballs, skillshots_dodged_per_min,
    damage_to_champions, damage_taken, augments, teammates (Riot IDs),
    fingerprint}]}]}. The fingerprint is the match_id — the extension
    computes it with the same formula as parse_profile_games, so a
    game imported here dedupes against the same game fetched by
    PlayARAM later.

    Raises ValueError on a structurally broken file. Returns
    (all_games, errors, total_exported). A player with zero usable
    games is an error entry (warning, not fatal) — the caller scores
    them from the cache. Unknown Riot IDs are skipped with a warning.
    A damage value of 0 means blank (a real Mayhem game never deals 0
    damage) — kept as None, skipped, never scored as 0."""
    try:
        raw = json.loads(Path(path).read_text())
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}")
    if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
        raise ValueError(f"{path} is not an extension export "
                         "(expected {\"players\": [...]}).")
    by_riot = {p.get("riot_id", "").lower(): p["name"] for p in players}
    by_name = {p["name"].lower(): p["name"] for p in players}
    all_games, errors = {}, []
    total_exported = 0
    for entry in raw["players"]:
        if not isinstance(entry, dict):
            continue
        name = (by_riot.get(str(entry.get("riot_id", "")).lower())
                or by_name.get(str(entry.get("display_name", "")).lower()))
        if not name:
            errors.append(f"Unknown player in export: "
                          f"{entry.get('riot_id') or entry.get('display_name') or '?'} — skipped.")
            continue
        games = []
        skipped = 0
        for g in entry.get("games") or []:
            try:
                champ = str(g["champion"]).strip()
                if not champ:
                    raise ValueError("no champion")
                mins = float(g["duration_minutes"])
                if mins <= 0:
                    raise ValueError("no duration")
                kills, deaths, assists = (int(g["kills"]), int(g["deaths"]),
                                          int(g["assists"]))
                date_s = str(g.get("date") or "").strip()
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_s):
                    raise ValueError("no date")
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue
            dmg = g.get("damage_to_champions")
            taken = g.get("damage_taken")
            try:
                dmg = int(dmg) or None
            except (TypeError, ValueError):
                dmg = None
            try:
                taken = int(taken) or None
            except (TypeError, ValueError):
                taken = None
            per_min = g.get("skillshots_dodged_per_min")
            try:
                per_min = float(per_min) if per_min is not None else None
            except (TypeError, ValueError):
                per_min = None
            if per_min is None and g.get("skillshots_dodged") is not None:
                try:
                    per_min = round(int(g["skillshots_dodged"]) / mins, 2)
                except (TypeError, ValueError, ZeroDivisionError):
                    per_min = None
            fingerprint = str(g.get("fingerprint") or "").strip()
            if not fingerprint:
                # Fallback, same formula as parse_profile_games.
                try:
                    dodged = int(g.get("skillshots_dodged"))
                except (TypeError, ValueError):
                    dodged = round((per_min or 0) * mins)
                cs = g.get("cs")
                try:
                    cs = int(cs)
                except (TypeError, ValueError):
                    cs = 0
                fingerprint = (f"{champ}|{kills}/{deaths}/{assists}|"
                               f"{mins:.1f}|{cs}|{dodged}|{date_s}")
            games.append({
                "match_id": fingerprint,
                "date": date_s,
                "champion": champ,
                "archetype": "Damage",  # filled in by the caller
                "win": bool(g.get("win")),
                "kills": kills, "deaths": deaths, "assists": assists,
                "damage_to_champions": dmg,
                "damage_taken": taken,
                "game_minutes": round(mins, 2),
                "dmg_share": None, "kp": None, "structure_share": None,
                "augments": [str(a).strip() for a in (g.get("augments") or [])
                             if str(a).strip()],
                "skillshots_dodged_per_min": per_min,
                "stack_size": None,
                "teammates": [str(t) for t in (g.get("teammates") or [])],
            })
        if skipped:
            errors.append(f"{name}: {skipped} exported game(s) were "
                          "missing fields and were skipped.")
        if not games:
            errors.append(f"{name}: 0 usable games in the export — "
                          "scoring from the cache.")
        all_games[name] = games
        total_exported += len(games)
    return all_games, errors, total_exported


def archive_broken_export(path):
    """Move a broken/empty extension export aside so the next run does
    not retry it. Best effort — a failure to move is not fatal."""
    try:
        p = Path(path)
        if not p.exists():
            return
        stamp = datetime.now(CST).strftime("%Y-%m-%d-%H%M")
        dest = p.with_name(f"extension-export-failed-{stamp}.json")
        p.rename(dest)
        print(f"Moved the broken export aside as {dest.name} — it will "
              "not be retried.")
    except Exception as e:
        print(f"Could not move the broken export aside ({e}) — it will "
              "be retried next run.")


# ---------------------------------------------------------------- main
# What the last run used, for the crash handler below (it records the
# source on the page when the updater dies unexpectedly).
CURRENT_SOURCE = "PlayARAM"


def set_automation(data, source, games_found, error):
    """Record how the last update attempt went, so the page can show it
    and nobody has to check the backend. Written even on failure."""
    now = datetime.now(CST)
    data.setdefault("meta", {})["automation"] = {
        "last_attempt": now.isoformat(),
        "last_attempt_label": now.strftime("%Y-%m-%d %I:%M %p CST"),
        "last_source": source,
        "last_games_found": games_found,
        "last_error": error,
        "next_update": "Daily at 12:00 AM CST (06:00 UTC), retry 12:30 AM CST",
        "needs_attention": bool(error),
    }


def main():
    global CSV_PATH, CURRENT_SOURCE
    dry_run = "--dry-run" in sys.argv
    from_csv = "--from-csv" in sys.argv
    from_extension = "--from-extension" in sys.argv
    csv_arg = None
    if from_csv:
        i = sys.argv.index("--from-csv")
        csv_arg = Path(sys.argv[i + 1]) if i + 1 < len(sys.argv) else CSV_PATH
    extension_arg = None
    if from_extension:
        i = sys.argv.index("--from-extension")
        extension_arg = (Path(sys.argv[i + 1]) if i + 1 < len(sys.argv)
                         else EXTENSION_EXPORT_PATH)
        CURRENT_SOURCE = "browser extension"
    elif from_csv:
        CURRENT_SOURCE = "manual CSV"

    players, window = load_players()
    data = json.loads(DATA_PATH.read_text())
    archetypes = champion_archetypes()
    all_games = {}
    # What the page's update note says, and any per-player problems.
    source_label = CURRENT_SOURCE
    mode_errors = None
    playaram_errors = None  # set in the PlayARAM branch; None in CSV mode

    if from_csv:
        CSV_PATH = csv_arg
        print(f"CSV mode: reading {CSV_PATH}")
        all_games = rows_from_csv()
        if not all_games:
            print("No usable rows in the CSV. Leaderboard unchanged.")
            set_automation(data, "manual CSV", 0, "CSV had no usable rows.")
            if not dry_run:
                DATA_PATH.write_text(json.dumps(data, indent=2))
            return 0
    elif from_extension:
        # Extension mode: the Chrome extension (extension/) read the 5
        # profiles in Natalie's own browser and downloaded one JSON
        # file, which she dropped in data/ as extension-export.json.
        # Merge it into the SAME per-player cache the PlayARAM
        # fetcher uses — same fingerprints, same dedupe — then score
        # exactly like the normal path. The workflow removes the file
        # after a successful import, so it is never imported twice.
        print(f"Extension mode: reading {extension_arg}")
        try:
            all_games, ext_errors, n_exported = rows_from_extension(
                extension_arg, players)
        except ValueError as e:
            print(f"Extension export is broken: {e}")
            print("Keeping the last snapshot — nothing was wiped.")
            set_automation(data, "browser extension", 0,
                           f"Extension export is broken: {e}")
            archive_broken_export(extension_arg)
            if not dry_run:
                DATA_PATH.write_text(json.dumps(data, indent=2))
            return 0
        if n_exported == 0:
            print("Extension export has 0 usable games for everyone.")
            print("Keeping the last snapshot — nothing was wiped.")
            set_automation(data, "browser extension", 0,
                           "; ".join(ext_errors) if ext_errors else
                           "Extension export had 0 usable games.")
            archive_broken_export(extension_arg)
            if not dry_run:
                DATA_PATH.write_text(json.dumps(data, indent=2))
            return 0
        mode_errors = "; ".join(ext_errors) if ext_errors else None
        riot_to_name = {p.get("riot_id", "").lower(): p["name"]
                        for p in players}
        total_new = 0
        for p in players:
            name = p["name"]
            games = all_games.get(name) or []
            if not games:
                # No usable games for this player in the export — score
                # from the cache, same as a failed PlayARAM fetch.
                all_games[name] = sorted(
                    load_playaram_cache(name),
                    key=lambda g: g.get("seq", 0), reverse=True)[:window]
                continue
            merged, n_new = merge_playaram_cache(name, games)
            total_new += n_new
            print(f"  {name}: {len(games)} games in export, {n_new} new, "
                  f"cache now {len(merged)}.")
            all_games[name] = merged[:window]
        # Teammates arrive as Riot IDs — keep only group members, as
        # display names. (Same mapping as the PlayARAM branch; the
        # cache on disk keeps the Riot IDs, so this is safe to repeat.)
        for name, games in all_games.items():
            for g in games:
                mates = sorted({riot_to_name[r.lower()]
                                for r in g.get("teammates", [])
                                if r.lower() in riot_to_name})
                g["teammates"] = mates
                g["stack_size"] = 1 + len(mates)
        print(f"Extension import: {n_exported} games exported, "
              f"{total_new} new in cache.")
    else:
        # PlayARAM mode: fetch each player's profile, parse the (up to)
        # 20 server-rendered games, merge into the per-player cache.
        print("PlayARAM mode: fetching profiles from playaram.gg (no Riot key needed).")
        now = datetime.now(CST)
        riot_to_name = {p.get("riot_id", "").lower(): p["name"]
                        for p in players}
        errors = []
        total_parsed = 0
        total_new = 0
        for p in players:
            name = p["name"]
            riot_id = p.get("riot_id", "")
            if not riot_id or "#" not in riot_id:
                print(f"Skipping {name}: no full Riot ID in players.yaml.")
                continue
            url = playaram_profile_url(riot_id, p.get("region", "na1"))
            print(f"{name} ({riot_id}) …", flush=True)
            try:
                html = fetch_profile_html(url)
            except PlayARAMBlocked as e:
                print(f"  BLOCKED — {e}", flush=True)
                errors.append(f"{name}: PlayARAM blocked the request "
                              "(Cloudflare) — page keeps its last numbers.")
                all_games[name] = sorted(
                    load_playaram_cache(name),
                    key=lambda g: g.get("seq", 0), reverse=True)[:window]
                continue
            except PlayARAMFetchError as e:
                print(f"  ERROR — {e}", flush=True)
                errors.append(f"{name}: {e}")
                all_games[name] = sorted(
                    load_playaram_cache(name),
                    key=lambda g: g.get("seq", 0), reverse=True)[:window]
                continue
            parsed, diag = parse_profile_games(html, riot_id, now)
            total_parsed += len(parsed)
            merged, n_new = merge_playaram_cache(name, parsed)
            total_new += n_new
            print(f"  {len(parsed)} games on profile "
                  f"({diag['segments']} cards, {diag['skipped']} skipped: "
                  f"{diag['no_kda']} no KDA, {diag['no_numbers']} no stats, "
                  f"{diag['no_champion']} no champion), "
                  f"{n_new} new, cache now {len(merged)}; "
                  f"augments on {diag['with_augments']}, "
                  f"participants on {diag['with_participants']}.", flush=True)
            # Archetype + stack: teammates arrive as Riot IDs — keep
            # only group members, as display names.
            for g in merged:
                g["archetype"] = archetype_for(g["champion"])
                mates = sorted({riot_to_name[r.lower()]
                                for r in g.get("teammates", [])
                                if r.lower() in riot_to_name})
                g["teammates"] = mates
                g["stack_size"] = 1 + len(mates)
            all_games[name] = merged[:window]
            print(f"  {len(all_games[name])} ARAM Mayhem games in window.")
        total_games = sum(len(g) for g in all_games.values())
        if total_games == 0:
            print("PlayARAM returned 0 usable games for everyone "
                  "(blocked, or no games parsed). Keeping the last "
                  "snapshot, not wiping it.")
            set_automation(data, "PlayARAM", 0,
                           "; ".join(errors) if errors else
                           "PlayARAM returned 0 usable games for everyone.")
            if not dry_run:
                DATA_PATH.write_text(json.dumps(data, indent=2))
            return 0
        playaram_errors = "; ".join(errors) if errors else None
        mode_errors = playaram_errors
        if errors:
            print(f"Note: {len(errors)} player(s) had fetch problems — "
                  "scoring the rest from cache. See the page's update note.")

    # CSV rows also need archetypes + a last-50 cut. PlayARAM rows
    # already have archetypes and a window cut; the loop is harmless
    # for them (archetype_for is idempotent, sort is by date).
    for name, games in all_games.items():
        for g in games:
            g["archetype"] = archetype_for(g["champion"])
        games.sort(key=lambda g: (g.get("seq", 0), g.get("date", "")),
                   reverse=True)
        all_games[name] = games[:window]

    annotate_stack(all_games)
    scored = score_players(all_games, archetypes)
    data["stack_splits"] = stack_splits(all_games)
    today = datetime.now(CST).strftime("%Y-%m-%d")
    now_label = datetime.now(CST).strftime("%Y-%m-%d %I:%M %p CST")

    scored_by_name = {k.lower(): v for k, v in scored.items()}
    for player in data["players"]:
        # Riot IDs / display names differ in case (PikabUwU vs pikabUwU) —
        # match case-insensitively so a player is never silently skipped.
        s = scored_by_name.get(player["name"].lower())
        if not s:
            continue
        player.update({
            "score": s["score"], "mmr_style": s["mmr_style"],
            "wins": s["wins"], "losses": s["losses"], "win_rate": s["win_rate"],
            "kda": s["kda"], "damage_per_min": s["damage_per_min"],
            "subscores": s["subscores"],
            "skillshots_dodged_per_min": s["skillshots_dodged_per_min"],
            "role_split": s.get("role_split"),
            "champion_focus": s.get("champion_focus"),
            "champion_top3": s.get("champion_top3", []),
            "champion_worst3": s.get("champion_worst3", []),
            "recent_20": s.get("recent_20"),
            "why_rank": s.get("why_rank"),
            "games": [public_game(g) for g in s["games"]],
        })

    # Highlights, from the fresh window. Damage is None when the source
    # has no damage data (PlayARAM) — show a blank, not a fake "0".
    ranked = sorted([p for p in data["players"] if p.get("score") is not None],
                    key=lambda p: p["score"], reverse=True)
    dmg_players = [p for p in data["players"]
                   if p.get("damage_per_min") is not None]
    if ranked:
        data["highlights"] = {
            "top_rated": {"player": ranked[0]["name"], "score": ranked[0]["score"],
                          "mmr_style": ranked[0]["mmr_style"]},
            "highest_damage_per_min": (
                {"player": max(dmg_players, key=lambda p: p["damage_per_min"])["name"],
                 "value": max(p["damage_per_min"] for p in dmg_players)}
                if dmg_players else {"player": None, "value": None}),
            "best_kda": {"player": max(
                data["players"], key=lambda p: p.get("kda") or 0)["name"],
                "value": max(p.get("kda") or 0 for p in data["players"])},
            "most_skillshots_dodged_per_min": {"player": max(
                data["players"], key=lambda p: p.get("skillshots_dodged_per_min") or 0)["name"],
                "value": max(p.get("skillshots_dodged_per_min") or 0 for p in data["players"])},
        }

    # Daily history: one point per day, never rewrite past points.
    hist = data.setdefault("history", [])
    if not any(h.get("date") == today for h in hist):
        hist.append({
            "date": today, "window_games": window,
            "scores": {p["name"]: p["score"] for p in data["players"] if p.get("score") is not None},
            "mmr_style": {p["name"]: p["mmr_style"] for p in data["players"] if p.get("mmr_style") is not None},
        })
    total_games = sum(len(s["games"]) for s in scored.values() if s)
    set_automation(data, source_label, total_games, mode_errors)
    data["meta"].update({
        "updated_at": datetime.now(CST).isoformat(),
        "updated_at_label": now_label,
        "window_games": window,
        "seed_note": "",
    })

    if dry_run:
        print("Dry run — would write:")
        print(json.dumps({p["name"]: p["score"] for p in data["players"]}, indent=2))
        return 0
    DATA_PATH.write_text(json.dumps(data, indent=2))
    print(f"Updated {DATA_PATH} — {now_label}, window = last {window} games each.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        # An unexpected crash — record it on the page so the group sees
        # it without checking the Action logs, then fail the run (red X).
        if "--dry-run" not in sys.argv:
            try:
                _data = json.loads(DATA_PATH.read_text())
                set_automation(_data, CURRENT_SOURCE, 0,
                               f"Updater crashed: {e}")
                DATA_PATH.write_text(json.dumps(_data, indent=2))
            except Exception:
                pass
        raise
