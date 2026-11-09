/* Options page: save + test the GitHub token.
   The token lives ONLY in chrome.storage.local. It is never logged,
   never printed, and never put into any message shown on screen. */

const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("save");
const testBtn = document.getElementById("test");
const statusEl = document.getElementById("status");

function show(msg, ok) {
  statusEl.textContent = msg;
  statusEl.className = ok ? "ok" : "err";
}

async function loadSaved() {
  try {
    const { githubToken } = await chrome.storage.local.get("githubToken");
    if (githubToken) tokenInput.value = githubToken; // masked by the password field
  } catch (e) { /* storage unavailable — field stays empty */ }
}

saveBtn.addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  try {
    if (token) {
      await chrome.storage.local.set({ githubToken: token });
      show("Saved. The next click on “Update leaderboard” will sync by itself.", true);
    } else {
      await chrome.storage.local.remove("githubToken");
      show("Token removed. The extension will download the file instead — drag it in as before.", true);
    }
  } catch (e) {
    show("Couldn't save — close and reopen the options page and try again.", false);
  }
});

testBtn.addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) {
    show("Paste your token first, then press Test.", false);
    return;
  }
  testBtn.disabled = true;
  saveBtn.disabled = true;
  show("Checking…", true);
  try {
    const result = await testGitHubToken(token);
    if (result.ok) {
      show("Token works — it can see the repo. Save it, then click “Update leaderboard” to sync.", true);
    } else {
      show(tokenTestMessage(result), false);
    }
  } catch (e) {
    show("Couldn't reach GitHub — check your internet and try again.", false);
  } finally {
    testBtn.disabled = false;
    saveBtn.disabled = false;
  }
});

loadSaved();
