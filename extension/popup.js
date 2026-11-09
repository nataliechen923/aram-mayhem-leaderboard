/* Popup: one button, per-player progress, and the next steps.
   State lives in the background worker and is mirrored to
   chrome.storage.session, so the popup shows the truth even if it
   was closed mid-run and reopened. */

const REPO_URL = "https://github.com/nataliechen923/aram-mayhem-leaderboard";

const goBtn = document.getElementById("go");
const statusEl = document.getElementById("status");
const listEl = document.getElementById("players");
const nextEl = document.getElementById("next");

// What each player's Load more step did, written by the content
// script into chrome.storage.session (keyed by display name) and
// read here in refresh(). Only shown for players whose row is done
// and whose stored game count matches the row — a stale record from
// an older run is never displayed.
let loadMoreDiag = {};

// One short line per player, e.g. "Load more ×2" or
// "Load more: button not found".
function loadMoreLine(d) {
  if (d.games_before_load_more >= 50) return "Load more not needed";
  if (!d.load_more_found) return "Load more: button not found";
  if (d.load_more_clicks > 0) return `Load more ×${d.load_more_clicks}`;
  return "Load more: button not found";
}

function render(state) {
  if (!state) return;
  goBtn.disabled = !!state.running;
  goBtn.textContent = state.running ? "Working…" : "Update leaderboard";

  listEl.innerHTML = "";
  for (const p of state.players) {
    const li = document.createElement("li");
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = p.display_name;
    const st = document.createElement("span");
    let cls = "";
    let txt = "Waiting";
    if (p.status === "loading") { cls = "busy"; txt = "Reading profile…"; }
    else if (p.status === "done") { cls = "done"; txt = `${p.games} games ✓`; }
    else if (p.status === "challenge") { cls = "bad"; txt = "Needs verification"; }
    else if (p.status === "error") { cls = "bad"; txt = p.note || "Error"; }
    st.className = "st " + cls;
    st.textContent = txt;
    const d = loadMoreDiag[p.display_name];
    if (p.status === "done" && d && d.games === p.games) {
      const br = document.createElement("br");
      const sm = document.createElement("small");
      sm.style.color = "var(--muted)";
      sm.textContent = loadMoreLine(d);
      st.appendChild(br);
      st.appendChild(sm);
    }
    li.appendChild(who);
    li.appendChild(st);
    listEl.appendChild(li);
  }

  statusEl.className = "";
  nextEl.style.display = "none";
  if (state.error && !state.done) {
    // Collection stopped early (challenge / page error).
    statusEl.className = "error";
    statusEl.textContent = state.error.message;
  } else if (state.done) {
    if (state.synced) {
      // One-click sync worked — nothing to drag, nothing to run.
      statusEl.className = "done";
      statusEl.textContent =
        `Done — ${state.total_games} games from all 5 players. Synced — the page rebuilds itself, give it a minute.`;
    } else {
      // Downloaded instead (no token saved, or the sync failed).
      // If the sync failed, say so in plain words first.
      if (state.error) {
        statusEl.className = "error";
        statusEl.textContent = state.error.message + " The file was downloaded instead — drag it in below.";
      } else {
        statusEl.className = "done";
        statusEl.textContent =
          `Done — ${state.total_games} games from all 5 players. File downloaded: ${state.filename}`;
      }
      nextEl.style.display = "block";
      nextEl.innerHTML =
        "<b>Next steps (about 1 minute):</b><br>" +
        "1. Rename the downloaded file to <code>extension-export.json</code>.<br>" +
        "2. On GitHub, open the repo's <code>data</code> folder and upload it there " +
        "(drag it in, then Commit).<br>" +
        "3. Go to the <b>Actions</b> tab → <b>Update leaderboard daily</b> → " +
        "<b>Run workflow</b>, wait for the green check, then reload the page.<br>" +
        `<a href="${REPO_URL}" target="_blank">Open the repo</a><br>` +
        `<span style="color:var(--muted)">Tip: add a token in the extension options and the next run will sync by itself — no dragging.</span>`;
    }
  } else if (state.running) {
    statusEl.textContent = "Going through the 5 profiles — keep this window open. Do not close the tabs it opens.";
  } else {
    statusEl.textContent = "";
  }
}

async function refresh() {
  try {
    const stored = await chrome.storage.session.get(["mayhemRun", "mayhemLoadMore"]);
    if (stored.mayhemLoadMore) loadMoreDiag = stored.mayhemLoadMore;
    if (stored.mayhemRun) { render(stored.mayhemRun); return; }
  } catch (e) { /* fall through to getState */ }
  try {
    const res = await chrome.runtime.sendMessage({ action: "getState" });
    if (res && res.state) render(res.state);
  } catch (e) { /* background not ready yet */ }
}

goBtn.addEventListener("click", async () => {
  goBtn.disabled = true;
  statusEl.textContent = "Starting…";
  try {
    await chrome.runtime.sendMessage({ action: "start" });
  } catch (e) {
    statusEl.className = "error";
    statusEl.textContent = "Could not start — close and reopen the popup, then try again.";
    goBtn.disabled = false;
  }
  refresh();
});

document.getElementById("opts").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && (changes.mayhemRun || changes.mayhemLoadMore)) refresh();
});

refresh();
