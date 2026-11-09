/* Content script — runs on PlayARAM profile pages, but does NOTHING
   on its own. It only collects when the background worker tells it to
   (after the user pressed "Update leaderboard" in the popup).

   What it does on a "collect" message:
   1. If the page is a Cloudflare challenge, it reports that and stops.
      It never attempts to solve or bypass the check.
   2. Clicks "Load more" (a normal in-page button, like the user
      clicking it) until 50 games are on the page or there is no more
      button: the button is scrolled into view first, and after each
      click the game count is polled every second for up to 10s, so a
      slow page still loads. If a click loads nothing new, it tries
      exactly one more click, then stops with the games it has.
   3. Parses the games out of the page with parser.js — the same rules
      as scripts/update.py, so fingerprints match.
   4. For each game, opens its Details panel (best effort) to read
      damage dealt/taken. If a panel cannot be opened or no confident
      numbers are found, damage stays null — never invented.
   5. Sends the games back to the background worker.

   It makes ZERO network requests of its own. It only reads the DOM of
   a page the user already opened in her own browser, and clicks the
   buttons on that page the way she would. */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (lo, hi) => lo + Math.random() * (hi - lo);

function findLoadMoreButton(doc) {
  // The real button is a plain <button> with the visible text
  // "Load more", no href, centered below the last game card — the
  // /load more/i match below is exactly right for it. While a batch
  // is loading the button disappears entirely (no "Loading..." text),
  // so this is only ever called after the game count has grown or
  // after the wait timed out — never during a load.
  const els = doc.querySelectorAll("button, a, [role='button']");
  for (const el of els) {
    const label = ((el.textContent || "") + " "
      + (el.getAttribute("aria-label") || "")).trim();
    if (!/load more/i.test(label)) continue;
    if (el.disabled) continue;
    if (el.tagName === "A") {
      const href = (el.getAttribute("href") || "").trim();
      if (href && href !== "#" && !href.startsWith("javascript:")) continue;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue; // hidden
    return el;
  }
  return null;
}

// After a Load more click, poll the parsed game count every second
// for up to 10s and return as soon as it grows. A fixed sleep was
// the bug: on the real page the new games can take longer than
// 2.5s to appear, and the old code then concluded the button had
// done nothing and stopped at 20 games.
async function waitForGrowth(before, riotId, now) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    await sleep(1000);
    if (isChallengePage(document)) return { challenge: true };
    const p = parseProfileGames(document.documentElement.outerHTML, riotId, now);
    if (p.games.length > before) return { parsed: p };
  }
  return { parsed: null }; // nothing new within 10s
}

// Diagnostics only: records what the Load more step did, so the
// popup can show one short line per player (e.g. "Load more: button
// not found"). Stored under the player's display name in
// chrome.storage.session — the background worker never touches it,
// and it is never part of the export. Never throws.
async function saveLoadMoreDiag(displayName, record) {
  try {
    if (typeof chrome === "undefined" || !chrome.storage
      || !chrome.storage.session) return;
    const cur = await chrome.storage.session.get("mayhemLoadMore");
    const map = (cur && cur.mayhemLoadMore) || {};
    map[displayName] = { ...record, at: new Date().toISOString() };
    await chrome.storage.session.set({ mayhemLoadMore: map });
  } catch (e) { /* diagnostics only — never break collection */ }
}

async function collect(riotId, displayName) {
  const now = new Date();
  if (isChallengePage(document)) {
    return { status: "challenge" };
  }
  // 1. Load more until 50 games are on the page (or no more button).
  let parsed = parseProfileGames(document.documentElement.outerHTML, riotId, now);
  const gamesBeforeLoadMore = parsed.games.length;
  let clicks = 0;
  let buttonFound = false;
  let stalled = false; // a click already failed to grow the list once
  while (parsed.games.length < 50 && clicks < 8) {
    const btn = findLoadMoreButton(document);
    if (!btn) break;
    buttonFound = true;
    const before = parsed.games.length;
    // The button sits at the bottom of a long list; bring it into
    // view first — on the real page a click on an off-screen control
    // can be ignored — then click it like the user would.
    btn.scrollIntoView({ block: "center" });
    await sleep(rand(400, 700));
    btn.click();
    clicks += 1;
    const grown = await waitForGrowth(before, riotId, now);
    if (grown.challenge) return { status: "challenge" };
    if (grown.parsed) {
      parsed = grown.parsed;
      stalled = false;
      // The button disappears while a batch loads and only comes
      // back once the new games are in; give it a beat to reappear
      // before looking for it again, so a still-hidden button is
      // never mistaken for "no more games".
      await sleep(rand(500, 900));
      continue;
    }
    // Nothing new arrived within 10s. Try exactly one more click;
    // if that also loads nothing, stop — the games already on the
    // page are still collected.
    if (stalled) break;
    stalled = true;
  }
  const games = parsed.games.slice(0, 50);
  const diag = {
    ...parsed.diag,
    load_more_clicks: clicks,
    load_more_found: buttonFound,
    games_before_load_more: gamesBeforeLoadMore,
    games_after_load_more: parsed.games.length,
  };
  await saveLoadMoreDiag(displayName, {
    games: games.length,
    load_more_found: buttonFound,
    load_more_clicks: clicks,
    games_before_load_more: gamesBeforeLoadMore,
    games_after_load_more: parsed.games.length,
  });

  // 2. Details panels for damage (best effort, null-safe).
  // Card roots are in document order (newest first), same as the
  // games — but the page can hold more cards than the 50-game cap,
  // so only the first 50 roots can belong to these games.
  const roots = findCardRoots(document).slice(0, games.length);
  diag.card_roots = roots.length;
  diag.with_damage = 0;
  diag.no_details_button = 0;
  if (roots.length === games.length) {
    for (let i = 0; i < games.length; i++) {
      const g = games[i];
      const root = roots[i];
      const btn = findDetailsButton(root);
      if (!btn) { diag.no_details_button += 1; continue; }
      const beforeText = root.innerText || "";
      btn.click();
      await sleep(rand(700, 1200));
      const afterText = root.innerText || "";
      const dmg = extractDamage(beforeText, afterText, g.champion, displayName);
      if (dmg.dealt !== null) g.damage_to_champions = dmg.dealt;
      if (dmg.taken !== null) g.damage_taken = dmg.taken;
      if (dmg.dealt !== null || dmg.taken !== null) diag.with_damage += 1;
    }
  } else {
    // Card roots and parsed games disagree — something about the page
    // layout changed. Do not guess which panel belongs to which game;
    // damage stays null and the diag says so.
    diag.damage_skipped = `card roots (${roots.length}) != games (${games.length})`;
  }
  return { status: "ok", games, diag };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.action !== "collect") return false;
  collect(msg.riot_id, msg.display_name)
    .then((res) => sendResponse(res))
    .catch((err) => sendResponse({
      status: "error",
      error: (err && err.message) || String(err),
    }));
  return true; // async reply
});
