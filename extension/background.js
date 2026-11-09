/* Background service worker — the part that opens the 5 profiles one
   at a time, asks the content script to read each page, and downloads
   the one export file at the end.

   Human-like by design: one tab at a time, a real page load plus a
   2–4 second pause before reading, a 1–2 second breather between
   players, 5 profile pages per run. The extension makes ZERO network
   requests to PlayARAM itself — it only reads pages the user's own
   browser opened, on her home connection. If a Cloudflare check
   appears, the run stops and waits for her to click the checkbox
   herself; it never tries to solve or bypass it. */

importScripts("players.js");

const COLLECT_TIMEOUT_MS = 180000; // Load more + 50 Details panels can take a while
const LOAD_TIMEOUT_MS = 60000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (lo, hi) => lo + Math.random() * (hi - lo);

let state = freshState();

function freshState() {
  return {
    running: false,
    started_at: null,
    players: MAYHEM_PLAYERS.map((p) => ({
      display_name: p.display_name,
      status: "waiting", // waiting | loading | done | challenge | error
      games: null,
      note: "",
    })),
    error: null, // { kind: "challenge" | "page" | "other", message }
    done: false,
    filename: null,
    total_games: 0,
  };
}

async function saveState() {
  try {
    await chrome.storage.session.set({ mayhemRun: state });
  } catch (e) { /* storage unavailable — popup falls back to getState */ }
  try {
    await chrome.runtime.sendMessage({ type: "mayhem-progress", state });
  } catch (e) { /* popup is closed; nothing listening */ }
}

function waitForTabLoad(tabId) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error("page did not finish loading in 60s"));
    }, LOAD_TIMEOUT_MS);
    function onUpdated(id, info) {
      if (id === tabId && info.status === "complete") { cleanup(); resolve(); }
    }
    function onRemoved(id) {
      if (id === tabId) {
        cleanup();
        reject(new Error("tab was closed before the page loaded"));
      }
    }
    function cleanup() {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.tabs.onRemoved.removeListener(onRemoved);
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.onRemoved.addListener(onRemoved);
  });
}

function sendCollect(tabId, player) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("the page did not answer — it may be showing a security check"));
    }, COLLECT_TIMEOUT_MS);
    chrome.tabs.sendMessage(
      tabId,
      { action: "collect", riot_id: player.riot_id, display_name: player.display_name },
      (res) => {
        clearTimeout(timer);
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(res);
      }
    );
  });
}

function localDateStr(d) {
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

async function runAll() {
  state = freshState();
  state.running = true;
  state.started_at = new Date().toISOString();
  await saveState();

  const collected = [];
  try {
    for (let i = 0; i < MAYHEM_PLAYERS.length; i++) {
      const player = MAYHEM_PLAYERS[i];
      const row = state.players[i];
      row.status = "loading";
      row.note = "Opening profile…";
      await saveState();

      const tab = await chrome.tabs.create({ url: player.url, active: true });
      try {
        await waitForTabLoad(tab.id);
      } catch (e) {
        row.status = "error";
        row.note = e.message;
        state.error = {
          kind: "page",
          message: `${player.display_name}: ${e.message}. The tab is still open — check what the page shows, then press the button again.`,
        };
        state.running = false;
        await saveState();
        return;
      }
      // Human-like pause: the page loaded; read it like a person would.
      await sleep(rand(2000, 4000));

      let res;
      try {
        res = await sendCollect(tab.id, player);
      } catch (e) {
        row.status = "error";
        row.note = "Page did not answer.";
        state.error = {
          kind: "page",
          message: `${player.display_name}: ${e.message}. The tab is still open — if it shows a "verify you are human" checkbox, click it, then press the button again.`,
        };
        state.running = false;
        await saveState();
        return;
      }

      if (!res || res.status === "challenge") {
        row.status = "challenge";
        row.note = "Waiting for verification.";
        state.error = {
          kind: "challenge",
          message: `PlayARAM is showing a "verify you are human" check on ${player.display_name}'s profile. The tab is still open — click the checkbox, then press "Update leaderboard" again to continue.`,
        };
        state.running = false;
        await saveState();
        return;
      }
      if (res.status !== "ok") {
        row.status = "error";
        row.note = res.error || "Could not read the page.";
        state.error = {
          kind: "other",
          message: `${player.display_name}: ${res.error || "could not read the page"}. The tab is still open — press the button again to retry.`,
        };
        state.running = false;
        await saveState();
        return;
      }

      collected.push({
        riot_id: player.riot_id,
        display_name: player.display_name,
        games: res.games || [],
      });
      row.status = "done";
      row.games = (res.games || []).length;
      row.note = `${row.games} games${(res.diag && res.diag.with_damage) ? `, damage on ${res.diag.with_damage}` : ""}`;
      state.total_games += row.games;
      await saveState();

      try { await chrome.tabs.remove(tab.id); } catch (e) { /* already closed */ }
      if (i < MAYHEM_PLAYERS.length - 1) await sleep(rand(1000, 2000));
    }
  } catch (e) {
    state.error = { kind: "other", message: `Stopped early: ${e.message}` };
    state.running = false;
    await saveState();
    return;
  }

  // All 5 done — download one file.
  const filename = `mayhem-extension-export-${localDateStr(new Date())}.json`;
  const payload = {
    exported_at: new Date().toISOString(),
    source: "extension",
    players: collected,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)],
    { type: "application/json" });
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({
      url, filename, saveAs: false, conflictAction: "overwrite",
    });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  state.filename = filename;
  state.done = true;
  state.running = false;
  await saveState();
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg) return false;
  if (msg.action === "start") {
    if (state.running) {
      sendResponse({ ok: false, reason: "already running" });
      return false;
    }
    runAll(); // async — the popup watches state via storage
    sendResponse({ ok: true });
    return false;
  }
  if (msg.action === "getState") {
    sendResponse({ ok: true, state });
    return false;
  }
  return false;
});
