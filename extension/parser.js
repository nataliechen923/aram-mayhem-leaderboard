/* PlayARAM profile parser — a JavaScript mirror of
   scripts/update.py's parse_profile_games(), so a game the extension
   reads gets the EXACT same fingerprint as the same game read by the
   server fetcher (same fingerprint = no duplicates when the two
   sources meet in the cache).

   Observed layout per game card (verified against the live site Nov 8):
     'ARAM: Mayhem' Victory|Defeat '14h ago' '26m 57s'
     champion portrait (alt = champion name) + level
     KDA as 10/2/15, then 5 numbers: CS, hats, event takedowns,
     snowballs hit, skillshots dodged   <-- in that display order
   Augment names come from img alt/title, excluding the champion
   portrait, item icons, and summoner spell icons (Mark / Flash).
   Participants come from /en/profile/<region>/<RiotID> links in DOM
   order — two teams of 5, the half containing the profile player is
   their team.

   This file is pure string parsing (no DOM), so it can be unit-tested
   in Node against synthetic HTML. The DOM helpers at the bottom
   (challenge detection, card roots, Details panel) live here too so
   the tests can exercise them in a headless browser. */

function normChamp(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function decodeEntities(s) {
  return (s || "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'");
}

/* '14h ago' / '1d ago' / 'just now' -> a Date in the browser's local
   timezone (Natalie's timezone), or null when there is no relative
   time at all. Mirrors update.py's _relative_to_date. */
function relativeToDate(text, now) {
  if (text.includes("just now")) return new Date(now);
  const m = text.match(/(\d+)\s*(min|h|d|w)\s*ago/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  const ms = { min: 60000, h: 3600000, d: 86400000, w: 604800000 }[m[2]];
  return new Date(now.getTime() - n * ms);
}

/* Format a Date as YYYY-MM-DD in fixed CST (UTC-6) — NOT the
   browser's local timezone. scripts/update.py uses a fixed CST too,
   so a game read by the extension gets the same date (and therefore
   the same fingerprint) as the same game read by the server fetcher,
   even in summer when Natalie's clock is on CDT (UTC-5). A date that
   differed by a day would break cache dedupe. */
function isoDate(d) {
  const cst = new Date(d.getTime() - 6 * 3600 * 1000);
  const p = (x) => String(x).padStart(2, "0");
  return `${cst.getUTCFullYear()}-${p(cst.getUTCMonth() + 1)}-${p(cst.getUTCDate())}`;
}

/* Pull the visible text (in order), img info (src/alt/title) and
   profile hrefs out of one raw HTML segment — the JS equivalent of
   update.py's _CardBits HTMLParser. */
function segmentBits(seg) {
  const imgs = [];
  const imgRe = /<img\b[^>]*>/gi;
  let m;
  while ((m = imgRe.exec(seg)) !== null) {
    const tag = m[0];
    const attr = (name) => {
      const am = tag.match(new RegExp(name + '\\s*=\\s*"([^"]*)"', "i"))
        || tag.match(new RegExp(name + "\\s*=\\s*'([^']*)'", "i"));
      return am ? decodeEntities(am[1]) : "";
    };
    imgs.push({ src: attr("src"), alt: attr("alt"), title: attr("title") });
  }
  const hrefs = [];
  const hrefRe = /<a\b[^>]*href\s*=\s*"([^"]*)"/gi;
  while ((m = hrefRe.exec(seg)) !== null) hrefs.push(decodeEntities(m[1]));
  const text = decodeEntities(seg.replace(/<[^>]*>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
  return { text, imgs, hrefs };
}

function parseProfileGames(html, riotId, now) {
  const diag = {
    segments: 0, parsed: 0, skipped: 0,
    no_kda: 0, no_numbers: 0, no_champion: 0,
    with_augments: 0, with_participants: 0,
  };
  // One card per 'ARAM: Mayhem' header. The page <title> says
  // 'ARAM Mayhem' (no colon), so it does not split there.
  const segments = html.split(/ARAM:\s*Mayhem/);
  const games = [];
  const meNorm = normChamp(riotId.replace("#", ""));
  for (const seg of segments.slice(1)) {
    diag.segments += 1;
    const bits = segmentBits(seg);
    const text = bits.text;
    const mWin = text.match(/\b(Victory|Defeat)\b/);
    const mDur = text.match(/(\d+)\s*m\s*(\d+)\s*s\b/);
    const mKda = text.match(/(\d+)\s*\/\s*(\d+)\s*\/\s*(\d+)/);
    let champ = null;
    let champKey = null;
    for (const img of bits.imgs) {
      const mim = img.src.match(/\/media\/champion\/(\d+)\.png/);
      if (mim) {
        champKey = mim[1];
        champ = (img.alt || "").trim() || null;
        break;
      }
    }
    if (!champ && champKey && typeof CHAMPION_BY_KEY !== "undefined") {
      champ = CHAMPION_BY_KEY[champKey] || null;
    }
    if (!mKda) { diag.no_kda += 1; diag.skipped += 1; continue; }
    if (!champ) { diag.no_champion += 1; diag.skipped += 1; continue; }
    const kills = parseInt(mKda[1], 10);
    const deaths = parseInt(mKda[2], 10);
    const assists = parseInt(mKda[3], 10);
    // The 5 numbers after the KDA: CS, hats, event takedowns,
    // snowballs hit, skillshots dodged — in that display order.
    const after = text.slice(text.indexOf(mKda[0]) + mKda[0].length);
    const nums = (after.match(/\b\d+\b/g) || []).slice(0, 5).map(Number);
    if (nums.length < 5) { diag.no_numbers += 1; diag.skipped += 1; continue; }
    const [cs, hats, eventTakedowns, snowballs, dodged] = nums;
    let mins = 0;
    if (mDur) mins = parseInt(mDur[1], 10) + parseInt(mDur[2], 10) / 60;
    if (mins < 5) { diag.skipped += 1; continue; } // remake under 5 minutes
    const date = relativeToDate(text, now);
    const dateS = date ? isoDate(date) : isoDate(now);
    // Augments: img alt/title, excluding the champion portrait,
    // item icons, and summoner spell icons (Mark / Flash). The class
    // icon (e.g. alt "HEAVY") is kept — the site's own Augments tab
    // names class + 4 augments per player.
    const augments = [];
    for (const img of bits.imgs) {
      const low = img.src.toLowerCase();
      if (low.includes("champion") || low.includes("item")
        || low.includes("spell") || low.includes("summoner")) continue;
      const name = (img.alt || img.title || "").trim();
      if (name && !augments.includes(name)) augments.push(name);
    }
    if (augments.length) diag.with_augments += 1;
    // Participants: /en/profile/<region>/<RiotID> links, in DOM
    // order — two groups of 5, one per team.
    const participants = [];
    for (const href of bits.hrefs) {
      const mp = href.match(/^\/en\/profile\/[a-z0-9]+\/([^"'/?#]+)/);
      if (mp) {
        let rid = mp[1];
        try { rid = decodeURIComponent(rid); } catch (e) { /* keep raw */ }
        if (!participants.includes(rid)) participants.push(rid);
      }
    }
    let teammates = [];
    if (participants.length >= 10) {
      diag.with_participants += 1;
      const teams = [participants.slice(0, 5), participants.slice(5, 10)];
      for (const team of teams) {
        if (team.some((r) => normChamp(r.replace("#", "")) === meNorm)) {
          teammates = team.filter(
            (r) => normChamp(r.replace("#", "")) !== meNorm);
          break;
        }
      }
    }
    // Same fingerprint formula as update.py — this is what dedupes
    // games in the cache, so it must match character for character.
    const fingerprint =
      `${champ}|${kills}/${deaths}/${assists}|${mins.toFixed(1)}|${cs}|${dodged}|${dateS}`;
    games.push({
      champion: champ,
      win: mWin ? mWin[1] === "Victory" : false,
      date: dateS,
      duration_minutes: Math.round(mins * 100) / 100,
      kills, deaths, assists,
      cs, hats, event_takedowns: eventTakedowns, snowballs,
      skillshots_dodged: dodged,
      skillshots_dodged_per_min: mins ? Math.round((dodged / mins) * 100) / 100 : null,
      damage_to_champions: null, // filled from the Details panel, if it opens
      damage_taken: null,
      augments,
      teammates,
      fingerprint,
    });
    diag.parsed += 1;
  }
  return { games, diag };
}

/* --- DOM helpers (content script only) --- */

/* True when the page is a Cloudflare challenge instead of the profile.
   The extension NEVER tries to solve or bypass this — it stops and
   tells the user to click the checkbox herself.
   Deliberately checks the page TITLE and VISIBLE text (innerText)
   only — never raw HTML. The extension's own scripts contain these
   same marker strings, and raw HTML would also match script content,
   so an outerHTML scan would false-positive on the extension itself. */
function isChallengePage(doc) {
  const title = (doc.title || "");
  if (title.includes("Just a moment")) return true;
  const text = (doc.body && doc.body.innerText) || "";
  if (text.includes("Just a moment")) return true;
  if (text.includes("Verify you are human")) return true;
  if (doc.querySelector('iframe[src*="challenges.cloudflare.com"]')) return true;
  return false;
}

/* The DOM element that is one game card: the highest ancestor of an
   "ARAM: Mayhem" text node that still contains exactly one such
   header. Returns the card roots in document order (newest first,
   same order parseProfileGames returns games in). */
function findCardRoots(doc) {
  const walker = doc.createTreeWalker(
    doc.body, NodeFilter.SHOW_TEXT, null);
  const roots = [];
  let node;
  const countHeaders = (el) =>
    (el.textContent.match(/ARAM:\s*Mayhem/g) || []).length;
  while ((node = walker.nextNode())) {
    if (!/ARAM:\s*Mayhem/.test(node.nodeValue)) continue;
    let el = node.parentElement;
    let best = el;
    while (el && el !== doc.body) {
      if (countHeaders(el) === 1) best = el;
      else break;
      el = el.parentElement;
    }
    if (best && !roots.includes(best)) roots.push(best);
  }
  return roots;
}

/* The control that expands a card's Details panel, if the card has
   one. Only real buttons (or links going nowhere) are returned — a
   link to another page is never clicked, so the extension cannot
   navigate away from the profile. */
function findDetailsButton(cardRoot) {
  const els = cardRoot.querySelectorAll("button, a, [role='button']");
  for (const el of els) {
    const label = ((el.textContent || "") + " "
      + (el.getAttribute("aria-label") || "") + " "
      + (el.getAttribute("title") || "")).trim();
    if (!/details/i.test(label)) continue;
    if (el.tagName === "A") {
      const href = (el.getAttribute("href") || "").trim();
      if (href && href !== "#" && !href.startsWith("javascript:")) continue;
    }
    if (el.disabled) continue;
    return el;
  }
  return null;
}

/* Read damage dealt / taken for the profile player out of an expanded
   Details panel (the card's text AFTER the panel was opened).
   Best effort only, and deliberately strict:
   - a "damage" line only counts if it was NOT already in the card
     before the panel was opened (beforeText guard);
   - prefer lines that also name the game's champion (and, better, the
     profile player's name) — the panel can list all 10 players;
   - values must be in a plausible range for one Mayhem game, or they
     are ignored (a missing number stays null, never a guessed one).
   Returns { dealt, taken } with nulls when nothing confident matches. */
function extractDamage(beforeText, afterText, champion, playerName) {
  const result = { dealt: null, taken: null };
  const hasDamageBefore = /damage/i.test(beforeText || "");
  if (hasDamageBefore) return result; // cannot tell panel text apart
  const lines = (afterText || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const numOf = (s) => {
    const nums = (s.match(/[\d,]+/g) || []).map((x) => parseInt(x.replace(/,/g, ""), 10));
    return nums.length ? nums[nums.length - 1] : null;
  };
  const pick = (re, lo, hi) => {
    const ranked = lines
      .map((line, i) => ({ line, i, score:
        (line.includes(champion) ? 2 : 0)
        + (playerName && line.toLowerCase().includes(playerName.toLowerCase()) ? 2 : 0) }))
      .filter((c) => re.test(c.line))
      .sort((a, b) => b.score - a.score || a.i - b.i);
    for (const c of ranked) {
      // Take the first number AFTER the label on that line, so a line
      // like "Damage Dealt 12,345 Damage Taken 18,901" gives 12,345
      // for dealt (not the 18,901 at the end of the line).
      const m = c.line.match(re);
      const afterLabel = m ? c.line.slice(m.index + m[0].length) : c.line;
      let nums = (afterLabel.match(/[\d,]+/g) || [])
        .map((x) => parseInt(x.replace(/,/g, ""), 10));
      let v = nums.length ? nums[0] : null;
      if (v === null && lines[c.i + 1]) v = numOf(lines[c.i + 1]); // label on its own line
      if (v !== null && v >= lo && v <= hi) return v;
    }
    return null;
  };
  result.dealt = pick(/damage\s*(dealt|to\s+champions?)/i, 500, 300000);
  result.taken = pick(/damage\s*taken/i, 500, 500000);
  return result;
}

/* Exported for Node tests (harmless in the browser). */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    normChamp, relativeToDate, isoDate, segmentBits, parseProfileGames,
    isChallengePage, findCardRoots, findDetailsButton, extractDamage,
  };
}
