/* Content script — runs on PlayARAM profile pages, but does NOTHING
   on its own. It only collects when the background worker tells it to
   (after the user pressed "Update leaderboard" in the popup).

   What it does on a "collect" message:
   1. If the page is a Cloudflare challenge, it reports that and stops.
      It never attempts to solve or bypass the check.
   2. Clicks "Load more" (a normal in-page button, like the user
      clicking it) until 50 games are on the page or there is no more
      button, waiting a human-like pause after each click.
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

async function collect(riotId, displayName) {
  const now = new Date();
  if (isChallengePage(document)) {
    return { status: "challenge" };
  }
  // 1. Load more until 50 games are on the page (or no more button).
  let parsed = parseProfileGames(document.documentElement.outerHTML, riotId, now);
  let clicks = 0;
  while (parsed.games.length < 50 && clicks < 8) {
    const btn = findLoadMoreButton(document);
    if (!btn) break;
    const before = parsed.games.length;
    btn.click();
    clicks += 1;
    await sleep(rand(1500, 2500));
    if (isChallengePage(document)) return { status: "challenge" };
    parsed = parseProfileGames(document.documentElement.outerHTML, riotId, now);
    if (parsed.games.length <= before) break; // button did nothing new
  }
  const games = parsed.games.slice(0, 50);
  const diag = { ...parsed.diag, load_more_clicks: clicks };

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
