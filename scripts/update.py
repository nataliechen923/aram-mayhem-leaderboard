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
    hit, skillshots dodged), augment names and item build names (best
    effort — they decide the role a game is judged in, see
    infer_game_role), and links to all 10 players' profiles (used
    for stack detection: the 5 players on the profile player's team).
  * Does NOT show: per-game damage dealt/taken, per-player turret
    takedowns, or match IDs. (Damage lives only in the expandable
    Details panel, which renders on demand — it is not in the HTML
    the updater fetches, confirmed Nov 8.) The extension opens
    each game's Details panel and reads damage dealt/taken, so
    extension games carry damage and the Output and Damage Taken
    criteria join the grade for them; server-fetched games have no
    damage, so those criteria stay blank for them. Conversion stays
    blank everywhere unless a manual CSV provides structure data.
    A game grade is the mean of the criteria available for that
    game. Missing data is never scored as 0.

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
    excluding the champion portrait and item icons; item build names
    the same way, from the item icons. If the markup does not expose
    them, augments stay [] (and the Augments component scores a
    neutral 50) and items stay [] (and the role falls back to the
    champion's tags). Stack comes from the 10 profile links in the
    card: the 5 links in the profile player's half are their team.
    Returns (games, diagnostics dict). Games are newest-first.
    """
    diag = {"segments": 0, "parsed": 0, "skipped": 0,
            "no_kda": 0, "no_numbers": 0, "no_champion": 0,
            "with_augments": 0, "with_items": 0, "with_participants": 0}
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
        # Items: the build icons (src contains "item"), alt/title is
        # the item name. The profile player's build is the card's
        # main row, so the first icons in DOM order are theirs;
        # cap at 7 (6 slots + trinket) so a layout change that
        # exposed other players' builds could not flood the list.
        # Items feed the role inference (tank vs AP vs AD vs
        # support build) — a name the maps do not know is neutral.
        items = []
        for src, alt, title in bits.imgs:
            if "item" not in src.lower():
                continue
            name = (alt or title or "").strip()
            if name and name not in items:
                items.append(name)
            if len(items) >= 7:
                break
        if items:
            diag["with_items"] += 1
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
        # Fingerprint: champion + KDA + duration + CS + skillshots
        # dodged. The date is deliberately NOT in it: the relative
        # time ("14h ago") is computed by truncating the hour bucket,
        # so the same match can be dated Nov 9 at the 00:20 run and
        # Nov 8 at the 10:40 run — and the updater then treats it as
        # a new game, duplicating it in the cache and breaking
        # full-stack grouping. Same formula as the extension's
        # parser.js and rows_from_extension below. The date is still
        # stored on the game (for display and the match key).
        fingerprint = (f"{champ}|{kills}/{deaths}/{assists}|{mins:.1f}|"
                       f"{cs}|{dodged}")
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
            "dmg_share": None, "taken_share": None,
            "kp": None, "structure_share": None,
            "augments": augments,
            "items": items,
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


_FP_DATE_RE = re.compile(r"\|\d{4}-\d{2}-\d{2}$")


def _fp_base(match_id):
    """The identity of a game, with any trailing |YYYY-MM-DD date
    stripped. Fingerprints used to carry the date, and the
    relative-time hour bucket could date the same match Nov 9 on one
    run and Nov 8 on the next — same champion|KDA|duration|CS|dodged
    under two dates is ONE game, not two. New fingerprints have no
    date, so the base is the identity either way."""
    return _FP_DATE_RE.sub("", str(match_id or "").strip())


def dedupe_games_by_identity(games):
    """Collapse copies of the same game that differ only by the
    fingerprint's trailing date (the Nov 9 duplicates: the same
    match was dated Nov 9 at the 00:20 run and Nov 8 at the 10:40
    run, so the cache held it twice and the window lost older
    games). Same champion|KDA|duration|CS|dodged = one game.
    Keeps the copy with the highest seq (its window position is the
    newest import of that game, and its date is the most recent
    run's dating) and copies damage dealt/taken from a dropped copy
    when the kept one has none — a game re-read by the extension
    can gain damage the first copy never had. The kept copy's
    match_id is normalized to the dateless fingerprint, so the old
    and new formats dedupe from here on. Returns the games sorted
    newest-first by seq."""
    by_base = {}
    for g in games:
        base = _fp_base(g.get("match_id"))
        cur = by_base.get(base)
        if cur is None:
            by_base[base] = g
            continue
        # Keep the higher-seq copy; rescue damage from the dropped one.
        if g.get("seq", 0) > cur.get("seq", 0):
            keep, drop = g, cur
        else:
            keep, drop = cur, g
        for field in ("damage_to_champions", "damage_taken"):
            if keep.get(field) is None and drop.get(field) is not None:
                keep[field] = drop[field]
        by_base[base] = keep
    out = list(by_base.values())
    for g in out:
        g["match_id"] = _fp_base(g.get("match_id"))
    out.sort(key=lambda g: g.get("seq", 0), reverse=True)
    return out


def load_playaram_cache(name):
    p = _cache_path(name)
    if p.exists():
        try:
            # Collapse any date-duplicates left from before the
            # fingerprint lost its date (in-memory only — the file
            # is rewritten clean by the next merge).
            return dedupe_games_by_identity(json.loads(p.read_text()))
        except Exception:
            return []
    return []


def merge_playaram_cache(name, new_games):
    """Merge freshly parsed games into the player's cache, deduped by
    fingerprint. Newest games get the highest seq numbers; the cache
    is capped at CACHE_KEEP. Returns (window games newest-first, n_new)."""
    cached = dedupe_games_by_identity(load_playaram_cache(name))
    seen = {_fp_base(g.get("match_id")) for g in cached}
    max_seq = max((g.get("seq", 0) for g in cached), default=0)
    added = 0
    for g in reversed(new_games):  # oldest first, so newest gets top seq
        if _fp_base(g["match_id"]) in seen:
            continue
        max_seq += 1
        g["seq"] = max_seq
        cached.append(g)
        seen.add(_fp_base(g["match_id"]))
        added += 1
    cached.sort(key=lambda g: g.get("seq", 0), reverse=True)
    cached = dedupe_games_by_identity(cached)[:CACHE_KEEP]
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


# ---------------------------------------------------------------- role inference
# A game's role is judged from what was actually played, not just the
# champion: champion + augments + items. Malphite can be built tank
# or AP, Seraphine AP or Support — the champion alone cannot tell.
#
# Rule (deterministic; extension/parser.js implements the same rule,
# and the two are cross-checked in tests):
#   votes start with 1 for the champion's tag archetype (the prior);
#   each role-indicative augment adds 1 vote for its role; each
#   role-indicative item adds 1 vote for its role. AP and AD items
#   both vote Damage; tank items vote Frontline; enchanter/support
#   items vote Support. Most votes wins; a tie falls back to the
#   champion's archetype, and if that is not among the tied roles,
#   Damage wins over Frontline over Support. One item or augment
#   alone can never flip a role (it only ties the prior, and the
#   prior wins ties) — it takes a build leaning the other way.
#   Boots, trinkets and consumables never vote. An augment or item
#   the maps do not know is neutral and adds no vote. A game with no
#   augments and no items falls back to the champion's tags, exactly
#   like the old behaviour.
#
# ITEM_ROLE was generated from Data Dragon 16.22.1 item.json (the
# same version the updater already uses): each item's tags decide its
# signal — tank items carry Health with Armor/MagicResist, AP items
# carry SpellDamage, AD items carry AttackDamage/CriticalStrike/
# AttackSpeed, and the enchanter + support-quest items are listed by
# name. Boots / trinkets / consumables are excluded. Regenerate it
# from a fresh item.json if the patch changes item tags or renames
# an item (e.g. Luden's Echo -> Luden's Companion, covered by the
# alias below). Keys are normalized names (lowercase, alphanumeric).
ITEM_ROLE = {
    "abyssalmask": "tank",
    "abyssalscepter": "ap",
    "actualizer": "ap",
    "aegisofthelegion": "tank",
    "aetherwisp": "ap",
    "amplifyingtome": "ap",
    "archangelsstaff": "ap",
    "ardentcenser": "support",
    "atmasimpaler": "ad",
    "atmasreckoning": "ad",
    "avariceblade": "ad",
    "axiomarc": "ad",
    "bandleglassmirror": "ap",
    "bandlepipes": "tank",
    "bannerofcommand": "ap",
    "bansheesveil": "ap",
    "bastionbreaker": "ad",
    "bfsword": "ad",
    "bilgewatercutlass": "ad",
    "blackcleaver": "ad",
    "blackfiretorch": "ap",
    "blackmistscythe": "support",
    "bladeoftheruinedking": "ad",
    "blastingwand": "ap",
    "blightingjewel": "ap",
    "bloodletterscurse": "ap",
    "bloodsong": "support",
    "bloodthirster": "ad",
    "bountyofworlds": "support",
    "brawlersgloves": "ad",
    "bulwarkofthemountain": "support",
    "caulfieldswarhammer": "ad",
    "celestialopposition": "support",
    "chempunkchainsword": "ad",
    "chemtechputrifier": "support",
    "cloakofagility": "ad",
    "cloakofstarrynight": "tank",
    "cosmicdrive": "ap",
    "crownoftheshatteredqueen": "ap",
    "cruelty": "ap",
    "cryptbloom": "ap",
    "crystallinebracer": "tank",
    "cull": "ad",
    "dagger": "ad",
    "darkseal": "ap",
    "dawncore": "support",
    "deadmansplate": "tank",
    "deathfiregrasp": "ap",
    "deathsdance": "ad",
    "demonicembrace": "ap",
    "demonkingscrown": "tank",
    "divinesunderer": "ad",
    "doransblade": "ad",
    "doransbow": "ad",
    "doranshelm": "tank",
    "doransring": "ap",
    "doransshield": "tank",
    "dreammaker": "support",
    "duskanddawn": "ap",
    "duskbladeofdraktharr": "ad",
    "echoesofhelia": "support",
    "eclipse": "ad",
    "edgeofnight": "ad",
    "emblemofvalor": "tank",
    "endlesshunger": "ad",
    "essencereaver": "ad",
    "evenshroud": "tank",
    "everfrost": "ap",
    "executionerscalling": "ad",
    "experimentalhexplate": "ad",
    "fatedashes": "ap",
    "feralflare": "ad",
    "fiendhunterbolts": "ad",
    "fiendishcodex": "ap",
    "flesheater": "ap",
    "forceofnature": "tank",
    "frostfang": "support",
    "frozenheart": "tank",
    "frozenmallet": "ad",
    "galeforce": "ad",
    "gamblersblade": "ad",
    "gargoylestoneplate": "tank",
    "glacialbuckler": "tank",
    "glacialshroud": "tank",
    "goldenspatula": "tank",
    "goredrinker": "ad",
    "guardianangel": "ad",
    "guardiansamulet": "ap",
    "guardiansblade": "ad",
    "guardiansdirk": "ad",
    "guardianshammer": "ad",
    "guardianshorn": "tank",
    "guardiansorb": "ap",
    "guardiansshroud": "ap",
    "guinsoosrageblade": "ap",
    "gunmetalgreaves": "ad",
    "harrowingcrescent": "support",
    "hauntingguise": "ap",
    "hearthboundaxe": "ad",
    "heartsteel": "tank",
    "hexcoremk1": "ap",
    "hexcoremk2": "ap",
    "hexdrinker": "ad",
    "hexopticsc44": "ad",
    "hextechalternator": "ap",
    "hextechgunblade": "ap",
    "hextechrevolver": "ap",
    "hextechrocketbelt": "ap",
    "hollowradiance": "tank",
    "horizonfocus": "ap",
    "hubris": "ad",
    "hullbreaker": "ad",
    "huntersmachete": "ad",
    "iceborngauntlet": "tank",
    "immortalshieldbow": "ad",
    "imperialmandate": "support",
    "infinityedge": "ad",
    "innervatinglocket": "ad",
    "ionicspark": "ad",
    "ironspikewhip": "ad",
    "jakshotheprotean": "tank",
    "kaenicrookern": "tank",
    "kircheisshard": "ad",
    "knightsvow": "tank",
    "krakenslayer": "ad",
    "lastwhisper": "ad",
    "leechingleer": "ap",
    "liandrystorment": "ap",
    "lichbane": "ap",
    "lifeline": "ad",
    "lifewellpendant": "tank",
    "lightningbraid": "tank",
    "locketoftheironsolari": "tank",
    "longsword": "ad",
    "lorddominiksregards": "ad",
    "lostchapter": "ap",
    "luckypick": "ap",
    "ludenscompanion": "ap",
    "ludensecho": "ap",
    "madredsbloodrazor": "ad",
    "malady": "ap",
    "malignance": "ap",
    "manamune": "ad",
    "mawofmalmortius": "ad",
    "mejaissoulstealer": "ap",
    "mercurialscimitar": "ad",
    "mikaelsblessing": "support",
    "moonstonerenewer": "support",
    "morellonomicon": "ap",
    "mortalreminder": "ad",
    "muramana": "ad",
    "nashorstooth": "ap",
    "navoriflickerblade": "ad",
    "navoriquickblades": "ad",
    "needlesslylargerod": "ap",
    "nightharvester": "ap",
    "noonquiver": "ad",
    "oblivionorb": "ap",
    "ohmwrecker": "ap",
    "opportunity": "ad",
    "overgrowth": "ad",
    "overlordsbloodmail": "ad",
    "pauldronsofwhiterock": "support",
    "perfecthexcore": "ap",
    "phage": "ad",
    "phantomdancer": "ad",
    "pickaxe": "ad",
    "profanehydra": "ad",
    "prototypehexcore": "ap",
    "prowlersclaw": "ad",
    "rabadonsdeathcap": "ap",
    "radiantvirtue": "tank",
    "rageknife": "ad",
    "randuinsomen": "tank",
    "rapidfirecannon": "ad",
    "ravenoushydra": "ad",
    "rectrix": "ad",
    "recurvebow": "ad",
    "redemption": "support",
    "relicshield": "support",
    "riftmaker": "ap",
    "riteofruin": "ap",
    "rodofages": "ap",
    "runaanshurricane": "ad",
    "runesteelspaulders": "support",
    "runicbulwark": "tank",
    "runiccompass": "support",
    "rylaiscrystalscepter": "ap",
    "scoutsslingshot": "ad",
    "seekersarmguard": "ap",
    "seraphsembrace": "ap",
    "serpentsfang": "ad",
    "serrateddirk": "ad",
    "seryldasgrudge": "ad",
    "shadowflame": "ap",
    "shardoftrueice": "support",
    "shieldofmoltenstone": "tank",
    "shieldoftherakkor": "ad",
    "shurelyasbattlesong": "support",
    "shurelyasreverie": "tank",
    "shusheismanajug": "ap",
    "silvermeredawn": "tank",
    "sineater": "tank",
    "solsticesleigh": "support",
    "spearofshojin": "ad",
    "spectralcutlass": "ad",
    "spectralsickle": "support",
    "spectrescowl": "tank",
    "spellthiefsedge": "support",
    "spiritoftheancientgolem": "tank",
    "spiritoftheelderlizard": "ad",
    "spiritofthespectralwraith": "ap",
    "spiritvisage": "tank",
    "staffofflowingwater": "support",
    "starksfervor": "ad",
    "statikkshiv": "ap",
    "steelshoulderguards": "support",
    "steelsigil": "ad",
    "steraksgage": "ad",
    "stinger": "ad",
    "stirringwardstone": "ap",
    "stormrazor": "ad",
    "stormsurge": "ap",
    "stridebreaker": "ad",
    "sunderedsky": "ad",
    "sunfireaegis": "tank",
    "sunfirecape": "tank",
    "swordofblossomingdawn": "ap",
    "swordofthedivine": "ap",
    "swordoftheoccult": "ad",
    "targonsbuckler": "support",
    "terminus": "ad",
    "theblackcleaver": "ad",
    "thebloodthirster": "ad",
    "thebrutalizer": "ad",
    "thecollector": "ad",
    "thegoldenspatula": "tank",
    "thornmail": "tank",
    "tiamat": "ad",
    "titanichydra": "ad",
    "towerpowerup": "ad",
    "trailblazer": "tank",
    "trinityforce": "ad",
    "tunneler": "ad",
    "twinmask": "tank",
    "twinshadows": "ap",
    "ultrahydra": "ad",
    "umbralglaive": "ad",
    "unendingdespair": "tank",
    "vampiricscepter": "ad",
    "verdantbarrier": "ap",
    "vigilantwardstone": "support",
    "voidimmolation": "tank",
    "voidstaff": "ap",
    "voltaiccyclosword": "ad",
    "warmogsarmor": "tank",
    "watchfulwardstone": "support",
    "willoftheancients": "ap",
    "witsend": "ad",
    "woogletswitchcap": "ap",
    "worldatlas": "support",
    "wriggleslantern": "ad",
    "youmuusghostblade": "ad",
    "yuntalwildarrows": "ad",
    "zazzaksrealmspike": "support",
    "zeal": "ad",
    "zekesconvergence": "tank",
    "zephyr": "ad",
    "zhonyashourglass": "ap",
    "zzrotportal": "tank",
}

# Augments the group actually takes, from the repo's own records
# (the trap-augment list in data.json and the HEAVY class icon the
# parser keeps). Anything not listed here falls through to the
# keyword check below; anything still unknown is neutral.
AUGMENT_ROLE = {
    "heavy": "Frontline",       # Mayhem class icon: the tank class
    "skilledsniper": "Damage",  # long-range damage augment
}

# Fallback for augment names the curated map does not know: short,
# safe substrings of the normalized (lowercase, alphanumeric) name.
# Frontline and Support are checked before Damage, and "mage" is
# checked last, so "attack damage" matches before "mage" does.
# Kept deliberately narrow — a name that matches nothing is neutral.
AUGMENT_KEYWORDS = [
    ("armor", "Frontline"), ("magicresist", "Frontline"),
    ("resistance", "Frontline"), ("maxhealth", "Frontline"),
    ("titanic", "Frontline"), ("bulwark", "Frontline"),
    ("juggernaut", "Frontline"), ("vanguard", "Frontline"),
    ("warden", "Frontline"),
    ("heal", "Support"), ("shield", "Support"), ("ally", "Support"),
    ("allies", "Support"), ("enchanter", "Support"),
    ("guardian", "Support"), ("mend", "Support"),
    ("abilitypower", "Damage"), ("magicdamage", "Damage"),
    ("marksman", "Damage"), ("assassin", "Damage"),
    ("artillery", "Damage"), ("attackdamage", "Damage"),
    ("critical", "Damage"), ("attackspeed", "Damage"),
    ("onhit", "Damage"), ("mage", "Damage"),
]


def item_role(name):
    """'tank' / 'ap' / 'ad' / 'support' for an item name, or None."""
    return ITEM_ROLE.get(_norm_champ(name)) if name else None


def augment_role(name):
    """'Damage' / 'Frontline' / 'Support' for an augment name, or None."""
    if not name:
        return None
    key = _norm_champ(name)
    if key in AUGMENT_ROLE:
        return AUGMENT_ROLE[key]
    for word, role in AUGMENT_KEYWORDS:
        if word in key:
            return role
    return None


def infer_game_role(game, champion_prior=None):
    """Damage / Frontline / Support for one game, from champion +
    augments + items (see the rule above). champion_prior is the
    champion's tag archetype; when omitted it is looked up."""
    prior = champion_prior or archetype_for(game.get("champion"))
    votes = {"Damage": 0, "Frontline": 0, "Support": 0}
    votes[prior] = votes.get(prior, 0) + 1
    for a in game.get("augments") or []:
        role = augment_role(a)
        if role:
            votes[role] += 1
    for it in game.get("items") or []:
        sig = item_role(it)
        if sig == "tank":
            votes["Frontline"] += 1
        elif sig in ("ap", "ad"):
            votes["Damage"] += 1
        elif sig == "support":
            votes["Support"] += 1
    best = max(votes.values())
    tied = [r for r, v in votes.items() if v == best]
    if prior in tied:
        return prior
    for role in ("Damage", "Frontline", "Support"):
        if role in tied:
            return role
    return prior


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
    """Fill in stack_size / teammates only for games that do not
    already carry them. main() maps each game's teammates (Riot IDs
    from the participant links, or display names) to group display
    names and sets stack_size = 1 + len(teammates) for every source,
    so this is only a safety net for games that somehow arrive
    without a teammates list (a manual CSV row, an old cache entry):
    those read as solo. It never overwrites a teammates list.

    The old version grouped games by match_id to find stackmates,
    but the fingerprint IS the match_id and it is unique per
    player-game, so every group was a singleton — and on the Nov 9
    10:45 scheduled run it overwrote every game's teammates with []
    and wiped kill participation (KP% went from 73.3 to None for
    everyone). Match grouping lives in compute_team_totals, which
    keys on (date, game_minutes, win, member set)."""
    for name, games in all_games.items():
        for g in games:
            if g.get("stack_size") is not None \
                    and g.get("teammates") is not None:
                continue
            mates = g.get("teammates") or []
            g["teammates"] = mates
            g["stack_size"] = 1 + len(mates)


def _norm_member_id(s):
    """One member key for a Riot ID or a display name: the part before
    '#', lowercased, alphanumerics only. 'Vincent Chan#NA1' and
    'Vincent Chan' both become 'vincentchan', so a teammates list
    works whether it still holds Riot IDs or main() already mapped
    them to display names."""
    local = str(s or "").split("#")[0]
    return "".join(ch for ch in local.lower() if ch.isalnum())


def compute_team_totals(all_games):
    """Percent damage dealt / taken and kill participation for each
    game, as shares of the game's team totals — the damage ranking
    factors and the Teamplay criterion.

    Definitions (the extension reads damage dealt/taken from each
    game's Details panel; the server fetch cannot, so most
    server-fetched games carry no damage at all):
      * damage dealt share = player's damage dealt / team damage dealt
      * damage taken share = player's damage taken / team damage taken
      * kill participation = (kills + assists) / team kills
    Team totals are the sum over the five group members' games for
    the same match. A match has no published ID — PlayARAM shows
    none, and the fingerprint is unique per player-game, so it
    cannot link teammates. The match key is therefore (date,
    game_minutes, win, the full set of group members in the game):
    the date and the duration (to the second) and the shared result,
    plus the teammates list the extension reads off the card's
    participant links (main() maps those Riot IDs to display names
    before this runs). In a full-stack game every member's game
    carries the same key, so the five games group together. A group
    is complete only when it holds exactly one game from every
    player in all_games and the member set is the whole group (a
    full stack); otherwise every share stays None. The damage shares
    additionally need a non-null damage value on all five games
    for that factor; kill participation needs only KDA, which every
    parsed game carries, so it fills for every complete full-stack
    match even when damage is still missing. When a share is
    unavailable the game falls back to a damage-per-minute
    percentile in the grade (damage factors) or skips Teamplay
    entirely (see score_players). Incomplete groups are common: a
    teammate's game can sit outside their own last-50 window, a
    2-3 stack has non-group teammates whose damage/kills are not in
    the cache, and the old cached games from before the extension
    read damage carry nulls. Two different full-stack matches on
    the same day with the same duration and result share a key —
    then the group holds two games per player and the shares stay
    None (safe: skipped, never wrong). A game whose teammates list
    is missing or partial cannot be linked to its teammates, so it
    never yields shares.
    Why team totals come from the cache, not the card DOM: the
    collapsed game card shows only the profile player's KDA — the
    other nine players' KDA is not in the card (only their champion
    icons and profile links). PlayARAM's Details panel does list
    KDA for all 10 players, but its exact layout has never been
    observed from here (the panel renders on demand and the live
    site is unreachable from this VM), so no panel KDA is parsed —
    guessing the layout could misattribute kills. The five members'
    cached games give the exact team totals for full-stack matches
    with no new DOM reading.
    Shares are stored as 0-1 fractions on the game dict
    (dmg_share / taken_share / kp); per-player percentages live in
    the player aggregates in score_players. Missing values are
    skipped, never scored as 0.
    """
    n_players = len(all_games)
    if n_players < 2:
        return
    # Shares are recomputed fresh on every run (the cache stores the
    # raw games with shares at None), so clear any shares a previous
    # call left behind first — otherwise a group that stops being
    # complete would keep a stale share.
    for games in all_games.values():
        for g in games:
            g["dmg_share"] = None
            g["taken_share"] = None
            g["kp"] = None
    by_key = {}
    for name, games in all_games.items():
        me = _norm_member_id(name)
        for g in games:
            mates = {_norm_member_id(t) for t in g.get("teammates") or []}
            mates.add(me)
            key = (g.get("date"), g.get("game_minutes"), bool(g.get("win")),
                   frozenset(mates))
            by_key.setdefault(key, []).append((name, g))
    for key, entries in by_key.items():
        names = [n for n, _ in entries]
        if len(entries) != n_players or len(set(names)) != n_players:
            continue  # not a complete full-stack match in this window
        if len(key[3]) != n_players:
            continue  # member set is not the whole group (a smaller stack)
        dealt_all = all(g.get("damage_to_champions") is not None
                        for _, g in entries)
        taken_all = all(g.get("damage_taken") is not None
                        for _, g in entries)
        if dealt_all:
            total = sum(g["damage_to_champions"] for _, g in entries)
            if total > 0:
                for _, g in entries:
                    g["dmg_share"] = g["damage_to_champions"] / total
        if taken_all:
            total = sum(g["damage_taken"] for _, g in entries)
            if total > 0:
                for _, g in entries:
                    g["taken_share"] = g["damage_taken"] / total
        # Kill participation: the five members ARE the team in a full
        # stack, so the sum of their kills is the team total. Needs
        # only KDA, so it fills even when damage is still missing.
        ka = [(g.get("kills"), g.get("assists")) for _, g in entries]
        if all(k is not None and a is not None for k, a in ka):
            team_kills = sum(k for k, _ in ka)
            if team_kills > 0:
                for (_, g), (k, a) in zip(entries, ka):
                    g["kp"] = (k + a) / team_kills


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


def _champion_why(champ, wins, losses):
    """One-line summary for a champion entry, keyed on the win-loss
    record only — no grade or delta numbers, one sentence, light
    wit. The page renders this instead of the old grade paragraph
    ("Grades X points above this player's own average..."). The
    mean_grade / delta_vs_overall fields stay in the data for
    anywhere the page still needs the numbers."""
    w, l = wins, losses
    if l == 0:
        return f"Undefeated on {champ} — {w}-{l}, and it shows."
    if w == 0:
        return f"Winless on {champ} — {w}-{l}. Maybe retire this one for now."
    if w > l:
        return f"Winning on {champ} — {w}-{l}. Keep it in the rotation."
    if w == l:
        return f"Even on {champ} — {w}-{l}. A coin flip."
    return f"Losing on {champ} — {w}-{l}. Worth a rethink."


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
      server-fetched games the grade blends KDA, Teamplay (when team
      totals exist), Death Quality and Augments; Output and Damage
      Taken join in only when the source provides damage. The
      extension reads damage dealt/taken from each game's Details
      panel (best effort, strict, null-when-unsure), so extension
      games carry it. Output is the player's share of team damage
      dealt when all five teammates' damage is known for the match
      (a complete full-stack group — see compute_team_totals),
      else damage per minute; Damage Taken is the same idea for
      damage taken, graded within the game's role archetype so a
      tank soaking damage is judged against other tanks, never
      against a carry's damage taken. Conversion joins in only
      when a manual CSV provides structure data. Mechanics
      (skillshots dodged per minute) is the 8th graded criterion,
      blended as a percentile within role like the others — a good
      dodger scores high even on a tank. The subscore still shows
      the raw dodges-per-minute number, which is what the page
      displays for it.
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
            g["taken_share"] = g.get("taken_share")
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
            g["taken_share"] = g.get("taken_share")
            g["kp"] = g.get("kp")
            g["structure_share"] = g.get("structure_share")

            # Damage dealt (Output): the share of team damage when the
            # full team's totals are known for the match, else damage
            # per minute. The share is the fairer measure (a 25-minute
            # game has more damage in it than an 18-minute one), but
            # it needs all five teammates' damage — most games only
            # have the per-minute number, so that is the fallback.
            if g.get("dmg_share") is not None:
                output = blended(arch, g["champion"], "dmg_share", g["dmg_share"])
            else:
                output = blended(arch, g["champion"], "dmg_per_min", g["dmg_per_min"])
            # Damage taken: the same idea for damage soaked — share of
            # team damage taken when the full team's totals are known,
            # else damage taken per minute. More damage taken scores
            # higher WITHIN the role: a tank soaking is judged against
            # other tanks, never against a carry's damage taken. A
            # carry who dives and takes lots of damage still pays for
            # the deaths through Death Quality, so the two criteria
            # balance each other.
            if g.get("taken_share") is not None:
                taken = blended(arch, g["champion"], "taken_share", g["taken_share"])
            else:
                taken = blended(arch, g["champion"], "taken_per_min", g["taken_per_min"])
            kda = blended(arch, g["champion"], "kda", g["kda"])
            teamplay = blended(arch, g["champion"], "kp", g["kp"])
            death_q = 100 - blended(arch, g["champion"], "deaths", g["deaths"])
            conversion = blended(arch, g["champion"], "structure_share", g["structure_share"])
            # Mechanics: skillshots dodged per minute, blended as a
            # percentile within role like every other criterion — a
            # good dodger scores high even on a tank, and a carry
            # who never dodges pays for it. Missing (a CSV without
            # the column) stays None and is skipped, never 0.
            mech = blended(arch, g["champion"], "skillshots_dodged_per_min",
                           g.get("skillshots_dodged_per_min"))
            if g.get("augments"):
                rates = [aug_wins.get(a, 0) / aug_games[a] for a in g["augments"] if aug_games.get(a, 0) >= 3]
                aug = (sum(rates) / len(rates) * 100) if rates else 50.0
                # Rescale augment win-rate (~35-65%) onto 0-100 for comparability.
                aug = max(0.0, min(100.0, (aug - 35) / 30 * 100))
            else:
                aug = 50.0
            parts = [p for p in [output, taken, kda, teamplay, death_q, conversion, aug, mech]
                     if p is not None]
            g["grade"] = sum(parts) / len(parts) if parts else 50.0
            g["subscores"] = {
                "output": round(output, 1) if output is not None else None,
                "damage_taken": round(taken, 1) if taken is not None else None,
                "kda_efficiency": round(kda, 1) if kda is not None else None,
                "teamplay": round(teamplay, 1) if teamplay is not None else None,
                "death_quality": round(death_q, 1) if death_q is not None else None,
                "conversion": round(conversion, 1) if conversion is not None else None,
                "augments": round(aug, 1),
                # The mechanics SUBSCORE stays the raw dodges-per-
                # minute number: the page renders it as "X per
                # minute" in the score breakdown, so a percentile
                # here would read as "55.0 per minute". The grade
                # above uses the blended percentile (mech), not this.
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
            "damage_taken_per_min": (
                round(statistics.mean(g["taken_per_min"] for g in games
                                      if g.get("taken_per_min") is not None))
                if any(g.get("taken_per_min") is not None for g in games) else None),
            "damage_dealt_share_pct": (
                round(100.0 * statistics.mean(g["dmg_share"] for g in games
                                              if g.get("dmg_share") is not None), 1)
                if any(g.get("dmg_share") is not None for g in games) else None),
            "damage_taken_share_pct": (
                round(100.0 * statistics.mean(g["taken_share"] for g in games
                                              if g.get("taken_share") is not None), 1)
                if any(g.get("taken_share") is not None for g in games) else None),
            "kill_participation_pct": (
                round(100.0 * statistics.mean(g["kp"] for g in games
                                              if g.get("kp") is not None), 1)
                if any(g.get("kp") is not None for g in games) else None),
            "deaths_per_game": (
                round(statistics.mean(g["deaths"] for g in games), 1)
                if games else None),
            "subscores": {k: round(statistics.mean(
                g["subscores"][k] for g in games if g["subscores"][k] is not None), 1)
                if any(g["subscores"][k] is not None for g in games) else None
                for k in ["output", "damage_taken", "kda_efficiency", "teamplay",
                          "death_quality", "conversion", "augments", "mechanics"]},
            "skillshots_dodged_per_min": (
                round(statistics.mean(g["skillshots_dodged_per_min"] for g in games
                                      if g.get("skillshots_dodged_per_min") is not None), 2)
                if any(g.get("skillshots_dodged_per_min") is not None for g in games) else None),
            "games": games,
        }

    # --- Evidence: role split, champion focus, why-this-rank ---
    sub_keys = ["output", "damage_taken", "kda_efficiency", "teamplay",
                "death_quality", "conversion", "augments", "mechanics"]
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
        # Champion rows for EVERY champion in the window (1+ games):
        # the top 3 needs 3+ games, but the worst 3 fills from
        # 2-game then 1-game champions when the 3+ pool is small
        # (see below), so the rows are built once for all of them.
        # "why" is a short one-line summary keyed on the win-loss
        # record only — no grade or delta numbers. The page renders
        # it instead of the old grade paragraph.
        champ_rows_all = []
        for champ in sorted({g["champion"] for g in games}):
            cg = [g for g in games if g["champion"] == champ]
            cg_mean = statistics.mean(g["grade"] for g in cg)
            cg_wins = sum(1 for g in cg if g["win"])
            cg_delta = round(cg_mean - mean_grade, 1)
            champ_rows_all.append({
                "champion": champ, "image": champion_image(champ),
                "games": len(cg),
                "wins": cg_wins, "losses": len(cg) - cg_wins,
                "win_rate": round(100.0 * cg_wins / len(cg), 1),
                "mean_grade": round(cg_mean, 1),
                "delta_vs_overall": cg_delta,
                "why": _champion_why(champ, cg_wins, len(cg) - cg_wins),
            })
        # The 3+ game pool: "take when offered" / "pass or swap" and
        # the top 3 all need a real sample, so they stay 3+ only.
        champ_rows = [c for c in champ_rows_all if c["games"] >= 3]
        take = [c for c in sorted(champ_rows, key=lambda c: c["delta_vs_overall"], reverse=True)
                if c["delta_vs_overall"] >= 4]
        pas = [c for c in sorted(champ_rows, key=lambda c: c["delta_vs_overall"])
               if c["delta_vs_overall"] <= -4]
        r["role_split"] = role_split
        r["champion_focus"] = {"take_when_offered": take, "pass_or_swap": pas}
        # Top 3 / worst 3 champions in this 50-game window, ranked by
        # mean grade. Both lists use a MINIMUM OF 2 GAMES — one game
        # is not a pattern, so 1-game champions stay out, but the
        # 3-game threshold left too small a pool (CreamiNataella had
        # only Milio + Nautilus at 3+, so her worst 3 was just her
        # top 3 reversed). At 2+ her pool is 11 champions and
        # everyone else's is 12-15, so both lists can be distinct.
        # HARD RULE: a champion in the top 3 NEVER appears in the
        # worst 3 — the worst 3 is the lowest-graded 2+ game
        # champions NOT in the top 3. Fewer than 3 if the pool runs
        # out — never padded with a top-3 champion.
        pool2 = [c for c in champ_rows_all if c["games"] >= 2]
        r["champion_top3"] = sorted(
            pool2, key=lambda c: c["mean_grade"], reverse=True)[:3]
        top_names = {c["champion"] for c in r["champion_top3"]}
        r["champion_worst3"] = sorted(
            [c for c in pool2 if c["champion"] not in top_names],
            key=lambda c: c["mean_grade"])[:3]

        # --- Recent 20: how to improve, from the freshest 20 games only ---
        # Everything here is computed strictly inside the player's most
        # recent 20 games: no comparison to the other 30 games in the
        # window, and no snapshot numbers. Pros/cons/tips are filled
        # in the second pass below, ranked within the player's OWN
        # recent-20 subscores — never against the group's averages.
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
            f"source provides for that game (KDA, teamplay, death "
            f"quality, augments and mechanics — skillshots dodged — "
            f"plus damage dealt and damage taken "
            f"when the extension has read the game's Details panel — "
            f"share of team damage on full-stack games, else damage per "
            f"minute — and conversion only when structure data exists), "
            f"graded within role and adjusted for champion — not from "
            f"one stat.")

    # --- Recent-20 pros/cons/tips: personal, from the player's OWN
    # recent-20 subscores only ---
    # Rank the player's graded criteria (all 0-100 percentiles, so
    # they compare like-for-like) by their recent-20 subscore:
    # strongest = pros, weakest = cons. No group average, no
    # comparison to the older 30 games, no snapshot numbers — so
    # every player gets guidance from their own freshest 20 games,
    # and different players get different pros/cons because their
    # strongest and weakest criteria differ. The tip for each
    # criterion names the player's own number, so the text differs
    # per player even when two players share a criterion. Mechanics
    # IS blended into the grade as a percentile, but its subscore
    # stays dodges per minute (what the page shows), not a 0-100
    # percentile, so it is not ranked here — the ranking compares
    # percentiles like-for-like.
    label = {"output": "Output", "damage_taken": "Damage taken",
             "kda_efficiency": "KDA efficiency",
             "teamplay": "Teamplay", "death_quality": "Death quality",
             "conversion": "Conversion", "augments": "Augments",
             "mechanics": "Mechanics"}
    tip_for = {"output": "focus on damage output and positioning to deal more damage",
               "damage_taken": "step forward and soak more damage for the team",
               "kda_efficiency": "trade less — fewer deaths for the kills you get",
               "teamplay": "join more fights to raise kill participation",
               "death_quality": "die less, and later in the game",
               "conversion": "turn won fights into turrets",
               "augments": "rethink augment picks — the ones taken lately are underperforming",
               "mechanics": "dodge more skillshots"}
    keep_for = {"output": "keep finding damage — your positioning is paying off",
                "damage_taken": "keep stepping forward and soaking for the team",
                "kda_efficiency": "keep trading like this — good kills for few deaths",
                "teamplay": "keep joining fights — your kill participation is strong",
                "death_quality": "keep staying alive — your deaths are low for your role",
                "conversion": "keep turning won fights into turrets",
                "augments": "keep drafting augments like these — they're performing"}
    ranked_keys = ["output", "damage_taken", "kda_efficiency", "teamplay",
                   "death_quality", "conversion", "augments"]
    for name, r in results.items():
        if not r or not r.get("recent_20"):
            continue
        rr = r["recent_20"]
        have = [(k, rr["subscores"][k]) for k in ranked_keys
                if rr["subscores"].get(k) is not None]
        have.sort(key=lambda kv: kv[1], reverse=True)
        if not have:
            continue
        n = len(have)
        n_pros = 2 if n >= 4 else 1
        n_cons = 2 if n >= 4 else 1
        pros = have[:n_pros]
        # Top and bottom are disjoint by construction (n >= 2 gives
        # distinct first/last entries); with a single criterion
        # there is no weakest to name.
        cons = have[-n_cons:] if n >= 2 else []
        for k, v in pros:
            rr["pros"].append(f"{label[k]} is your strongest area in the last 20 ({v}) — keep it up.")
            rr["tips"].append(f"Keep up {label[k]} ({v} in the last 20): {keep_for[k]}.")
        for k, v in cons:
            rr["cons"].append(f"{label[k]} is your weakest area in the last 20 ({v}) — the thing to work on.")
            rr["tips"].append(f"Work on {label[k]} ({v} in the last 20): {tip_for[k]}.")
    return results


def public_game(g):
    return {
        "match_id": g["match_id"], "date": g["date"], "champion": g["champion"],
        "win": g["win"], "kills": g["kills"], "deaths": g["deaths"],
        "assists": g["assists"], "damage_to_champions": g["damage_to_champions"],
        "damage_taken": g["damage_taken"], "augments": g.get("augments", []),
        "game_minutes": round(g["game_minutes"], 1),
        "grade": round(g["grade"], 1),
        "damage_dealt_share_pct": (
            round(100.0 * g["dmg_share"], 1) if g.get("dmg_share") is not None else None),
        "damage_taken_share_pct": (
            round(100.0 * g["taken_share"], 1) if g.get("taken_share") is not None else None),
        "kill_participation_pct": (
            round(100.0 * g["kp"], 1) if g.get("kp") is not None else None),
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
                    "dmg_share": None, "taken_share": None,
                    "kp": None, "structure_share": None,
                    "augments": [a.strip() for a in (row.get("augments") or "").split(";") if a.strip()],
                    # Optional column ("items", ;-separated). A CSV
                    # without it scores roles from the champion alone.
                    "items": [i.strip() for i in (row.get("items") or "").split(";") if i.strip()],
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
    damage_to_champions, damage_taken, augments, items, archetype
    (the role the extension inferred from champion + augments +
    items), teammates (Riot IDs), fingerprint}]}]}. The fingerprint
    is the match_id — the extension computes it with the same formula
    as parse_profile_games, so a game imported here dedupes against
    the same game fetched by PlayARAM later.

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
                # Fallback, same formula as parse_profile_games:
                # champion + KDA + duration + CS + skillshots dodged,
                # NO date (the relative-time hour bucket can flip a
                # game's computed date across midnight, which
                # duplicated matches in the cache). The date is still
                # stored on the game.
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
                               f"{mins:.1f}|{cs}|{dodged}")
            # The extension already inferred the role from champion +
            # augments + items; keep it when it is a valid archetype,
            # otherwise the caller recomputes it (same rule).
            arch = str(g.get("archetype") or "").strip()
            if arch not in ("Damage", "Frontline", "Support"):
                arch = "Damage"  # filled in by the caller
            games.append({
                "match_id": fingerprint,
                "date": date_s,
                "champion": champ,
                "archetype": arch,
                "win": bool(g.get("win")),
                "kills": kills, "deaths": deaths, "assists": assists,
                "damage_to_champions": dmg,
                "damage_taken": taken,
                "game_minutes": round(mins, 2),
                "dmg_share": None, "taken_share": None,
                "kp": None, "structure_share": None,
                "augments": [str(a).strip() for a in (g.get("augments") or [])
                             if str(a).strip()],
                "items": [str(i).strip() for i in (g.get("items") or [])
                          if str(i).strip()],
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


# What the page shows under "How the rating works". The updater
# writes this into data.json on every run, so the explanation always
# matches the scoring code — edit the words here, not in data.json.
RANKING_METHOD = {
    "title": "How the ranking is fair — whole performance, role-adjusted, champion-adjusted",
    "one_line": "No single stat decides the rank. Every game is graded on the criteria the data source provides for that game, each graded only against players who played the same role in that game, and then adjusted for the champion played.",
    "points": [
        "Role first, judged from the game itself: a game's role (Damage, Frontline or Support) comes from the champion plus the augments taken and the items built — not the champion alone. Malphite built AP counts as Damage; Seraphine built with enchanter items counts as Support. Every component is a percentile WITHIN that role across all player-games in the window. A tank with 8 kills can score 90th percentile for Frontline while a carry with 12 kills scores only 60th for Damage. Raw kills and damage never compare a tank to a carry. A game with no augments or items recorded falls back to the champion's usual role.",
        "Champion second: each component is blended 70% archetype percentile + 30% same-champion percentile (only when the group has 3+ games on that champion; otherwise archetype only). Playing a champion well *for that champion* counts, not just picking a strong champion.",
        "Whole performance, not one stat: a game grade is the mean of the criteria available for that game — KDA Efficiency, Teamplay, Death Quality and Augments, plus Output (damage dealt) and Damage Taken when the extension has read the game's Details panel in your browser. Output is your share of the team's damage dealt when all five teammates' damage is known for the match (full-stack games), otherwise damage per minute; Damage Taken is the same idea for damage you soaked, judged within your role — a tank soaking damage is compared with other tanks, never with a carry's damage taken. Teamplay (kill participation: your kills + assists ÷ team kills) also comes from the five members' games, so it only has a value on full-stack games where everyone queued together. PlayARAM's own match list does not show damage, so games from a server fetch have no damage and those two criteria stay blank for them. Conversion joins in only when per-player structure data exists (a manual CSV). Mechanics (skillshots dodged per minute) is the 8th graded criterion, blended as a percentile within role like the others — a good dodger scores high even on a tank. The page also shows the raw dodges-per-minute number for context. KDA is 1 of the graded criteria, damage is only part of Output, and win rate is only 15% of the final score. A missing field is skipped, never scored as 0.",
        "Consistency counts: Performance Score = 55% mean game grade + 20% median grade + 10% floor (25th percentile) grade + 15% win rate. One pop-off game can't carry a rank; a low floor pulls it down.",
        "Evidence on every card: each player card shows their subscores vs the group average, their grade split by role played, their best / worst champions vs their own average (with game counts), and a 'Why this rank' paragraph built from those numbers — so a complaint can be answered with the breakdown, not an opinion.",
    ],
    "criteria_weights": "Each available criterion counts equally inside a game grade. Win rate is 15% of the final Performance Score, not the ranking itself.",
    "archetypes": {
        "Damage": "ADC / mage / assassin carries — judged on damage, kills and carry output",
        "Frontline": "Tanks / fighters — judged on damage taken, damage soaked per death, and frontline output",
        "Support": "Enchanters / wardens — judged on assists, teamplay and support output, not carry damage",
    },
}


# The per-criterion explainer the page shows under "How the Rating
# Works". Written into data.json on every run (next to
# ranking_method), so the wording here is the wording on the page —
# it used to live only in the seeded data.json, which is how a stale
# line ("Output … fills from a manual CSV") survived long after the
# extension started reading damage from the Details panel.
HOW_RATING_WORKS = {
    "criteria": [
        "Output — damage dealt per minute, or your share of your team's damage dealt when all five teammates' damage is known for the match (full-stack games) — graded within your role archetype (Damage / Frontline / Support). Damage comes from the extension reading each game's Details panel in your browser; PlayARAM's match list does not show damage, so games from a server fetch stay blank for Output (a missing field is skipped, never scored as 0).",
        "Damage taken — damage you took: your share of your team's damage taken when all five teammates' damage is known for the match, else damage taken per minute — graded within your role archetype, so a tank soaking damage is judged against other tanks, never against a carry's damage taken. Same Details-panel source as Output.",
        "KDA efficiency — kills, deaths and assists weighed against the archetype's expected line.",
        "Teamplay — kill participation: (kills + assists) ÷ team kills. Team kills come from the five group members' games for the same match, so this only has a value on full-stack games where everyone queued together; other games skip it (a missing field is skipped, never scored as 0).",
        "Death quality — deaths per game, graded within role (fewer deaths is better).",
        "Conversion — your share of your team's structure takedowns (turrets + inhibitors ÷ team total). Only when per-player structure data exists — not shown on PlayARAM's match list, so it stays blank from PlayARAM.",
        "Augments — how the augments you drafted performed across the group's games in this window. PlayARAM names are read from the match list when the page exposes them; otherwise this scores a neutral 50.",
        "Mechanics — skillshots dodged per minute, graded as a percentile within your role archetype like the other criteria (the page also shows the raw dodges-per-minute number).",
    ],
    "formula": "Performance Score = 55% mean game grade + 20% median grade + 10% floor (25th percentile) grade + 15% win rate",
    "mmr_formula": "MMR-style = 800 + Performance Score × 14 — 1500 is roughly average",
    "not_measured": "PlayARAM does not publish healing, shielding, crowd-control score or per-player objective damage, so none of those appear here.",
}


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
        # Teammates are mapped to display names in the shared loop
        # below (once, for every source — including players whose
        # games came from the cache here).
        print(f"Extension import: {n_exported} games exported, "
              f"{total_new} new in cache.")
        # Record that this data came from a real extension sync, so the
        # page can show a "Synced via extension" chip. Only set on a
        # successful import — this point is past both failure exits
        # above (broken export, 0 usable games). A PlayARAM fetch or a
        # manual CSV never touches it, and a later non-extension run
        # leaves the last successful sync time in place.
        sync_now = datetime.now(CST)
        data.setdefault("meta", {})["last_extension_sync"] = \
            sync_now.isoformat()
        data["meta"]["last_extension_sync_label"] = sync_now.strftime(
            "%Y-%m-%d %I:%M %p CST")
    else:
        # PlayARAM mode: fetch each player's profile, parse the (up to)
        # 20 server-rendered games, merge into the per-player cache.
        print("PlayARAM mode: fetching profiles from playaram.gg (no Riot key needed).")
        now = datetime.now(CST)
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
                  f"items on {diag.get('with_items', 0)}, "
                  f"participants on {diag['with_participants']}.", flush=True)
            # Role (from champion + augments + items) for the fresh
            # games; teammates are mapped to display names in the
            # shared loop below (once, for every source — including
            # players whose fetch was blocked and scored from cache).
            for g in merged:
                g["archetype"] = infer_game_role(g)
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

    # Every game gets its role from champion + augments + items
    # (infer_game_role), whichever source it came from — PlayARAM,
    # CSV or extension. The loop is idempotent, and the sort + window
    # cut apply to all sources. Teammates are mapped here too, once
    # for every source: the old code mapped them inside each branch's
    # per-player loop, so a blocked PlayARAM fetch (which loads from
    # cache and continues) skipped the mapping entirely, and
    # annotate_stack then overwrote teammates with [] and wiped KP%
    # (Nov 9 10:45: KP% went from 73.3 to None for everyone).
    # Teammates arrive as Riot IDs (participant links, extension
    # export) or already as display names (a cache a previous run
    # mapped, a manual CSV) — both forms are accepted, because a
    # display name alone is NOT a key in riot_to_name, so a naive
    # re-map would wipe already-mapped names. Unknown IDs are
    # dropped, never kept as-is.
    riot_to_name = {p.get("riot_id", "").lower(): p["name"]
                    for p in players}
    name_to_name = {_norm_member_id(p["name"]): p["name"]
                    for p in players}
    for name, games in all_games.items():
        for g in games:
            g["archetype"] = infer_game_role(g)
            mates = set()
            for t in (g.get("teammates") or []):
                low = str(t).lower()
                if low in riot_to_name:
                    mates.add(riot_to_name[low])
                elif _norm_member_id(t) in name_to_name:
                    mates.add(name_to_name[_norm_member_id(t)])
            mates.discard(name)
            g["teammates"] = sorted(mates)
            g["stack_size"] = 1 + len(mates)
        games.sort(key=lambda g: (g.get("seq", 0), g.get("date", "")),
                   reverse=True)
        all_games[name] = games[:window]

    annotate_stack(all_games)
    # Team totals for the percent-damage ranking factors and kill
    # participation: a match group only yields shares when all five
    # teammates' games are in the window (see compute_team_totals).
    # Must run before score_players, which reads dmg_share /
    # taken_share / kp.
    compute_team_totals(all_games)
    scored = score_players(all_games, archetypes)
    data["stack_splits"] = stack_splits(all_games)
    data["ranking_method"] = RANKING_METHOD
    data["how_rating_works"] = HOW_RATING_WORKS
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
            "damage_taken_per_min": s["damage_taken_per_min"],
            "damage_dealt_share_pct": s["damage_dealt_share_pct"],
            "damage_taken_share_pct": s["damage_taken_share_pct"],
            "kill_participation_pct": s["kill_participation_pct"],
            "deaths_per_game": s["deaths_per_game"],
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
        # The Nov 8 seed shipped a snapshot note ("Snapshot evidence
        # above is from Nov 8…") that no run ever overwrote, so it
        # kept shipping after real runs. The page does not display
        # it; drop it on a real run rather than leave stale text.
        player.pop("evidence_note", None)
        # Same story for the seed's damage_share_pct (a Nov 8
        # snapshot number, e.g. 21.9 for I3i3oy): nothing reads or
        # writes it, and the new share fields are
        # damage_dealt_share_pct / damage_taken_share_pct. Drop it
        # so the stale number cannot be confused with the new ones.
        player.pop("damage_share_pct", None)

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
