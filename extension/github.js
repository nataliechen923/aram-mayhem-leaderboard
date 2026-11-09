/* GitHub API helper — commits the extension's export straight to the
   repo, so one click in the popup can sync the leaderboard with no
   file dragging and no manual workflow run.

   SECURITY: the token is read from chrome.storage.local at call time
   and is NEVER logged, printed, stored anywhere else, or included
   in any returned message. All errors come back as plain-words
   kinds ("auth" | "repo" | "other") — never with the token, the
   response body, or any credential in them.

   API_BASE is overridable (globalThis.__MAYHEM_API_BASE) ONLY so
   tests can point it at a local mock server. In the real extension
   it is always https://api.github.com. */

const MAYHEM_REPO = "nataliechen923/aram-mayhem-leaderboard";
const MAYHEM_BRANCH = "main";
const MAYHEM_EXPORT_PATH = "data/extension-export.json";

function githubApiBase() {
  if (typeof globalThis !== "undefined" && globalThis.__MAYHEM_API_BASE) {
    return globalThis.__MAYHEM_API_BASE;
  }
  return "https://api.github.com";
}

/* Base64-encode a UTF-8 string. Chunked so a large export (50 games
   x 5 players) never blows the call stack. Uses Buffer in Node (tests)
   and TextEncoder + btoa in the browser/service worker. */
function b64encodeUtf8(str) {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(str, "utf8").toString("base64");
  }
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

function githubHeaders(token) {
  return {
    "Authorization": "Bearer " + token,
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
  };
}

/* Check the token can see the repo (used by the options page "Test"
   button). 200 = good. 401/403 = token problem. 404 = repo not found
   or the token has no access to it. Anything else / network error =
   "other". Never returns the token or any response body. */
async function testGitHubToken(token) {
  let res;
  try {
    res = await fetch(`${githubApiBase()}/repos/${MAYHEM_REPO}`, {
      headers: githubHeaders(token),
    });
  } catch (e) {
    return { ok: false, kind: "other", status: 0 };
  }
  if (res.status === 200) return { ok: true };
  if (res.status === 401 || res.status === 403) {
    return { ok: false, kind: "auth", status: res.status };
  }
  if (res.status === 404) return { ok: false, kind: "repo", status: 404 };
  return { ok: false, kind: "other", status: res.status };
}

/* Commit the export payload to data/extension-export.json.
   Single attempt only — no retries, no loops. Flow:
   GET the file first: 200 gives us its SHA (needed to overwrite),
   404 means it is a new file (no SHA needed). Then PUT the new
   content. Returns { ok: true } or { ok: false, kind, status }.
   kind: "auth" = token problem; "repo" = repo/path not found;
   "other" = anything else (network, validation, GitHub error). */
async function commitExportToGitHub(token, payload, dateStr) {
  const json = JSON.stringify(payload, null, 2);
  const url = `${githubApiBase()}/repos/${MAYHEM_REPO}/contents/${MAYHEM_EXPORT_PATH}?ref=${MAYHEM_BRANCH}`;
  let sha = null;
  try {
    const getRes = await fetch(url, { headers: githubHeaders(token) });
    if (getRes.status === 200) {
      const body = await getRes.json();
      sha = body && body.sha ? body.sha : null;
    } else if (getRes.status === 404) {
      sha = null; // new file
    } else if (getRes.status === 401 || getRes.status === 403) {
      return { ok: false, kind: "auth", status: getRes.status };
    } else {
      return { ok: false, kind: "other", status: getRes.status };
    }
  } catch (e) {
    return { ok: false, kind: "other", status: 0 };
  }

  const body = {
    message: `Extension export ${dateStr}`,
    content: b64encodeUtf8(json),
    branch: MAYHEM_BRANCH,
  };
  if (sha) body.sha = sha;

  let putRes;
  try {
    putRes = await fetch(
      `${githubApiBase()}/repos/${MAYHEM_REPO}/contents/${MAYHEM_EXPORT_PATH}`,
      { method: "PUT", headers: githubHeaders(token), body: JSON.stringify(body) }
    );
  } catch (e) {
    return { ok: false, kind: "other", status: 0 };
  }
  if (putRes.status === 200 || putRes.status === 201) return { ok: true };
  if (putRes.status === 401 || putRes.status === 403) {
    return { ok: false, kind: "auth", status: putRes.status };
  }
  if (putRes.status === 404) return { ok: false, kind: "repo", status: 404 };
  return { ok: false, kind: "other", status: putRes.status };
}

/* Plain-words message for a failed commit. No token, no status
   code, no response detail — just what to do next. */
function syncErrorMessage(result) {
  if (!result) return "GitHub didn't accept the file — the download is below, drag it in instead.";
  if (result.kind === "auth") {
    return "The token didn't work — check it in the extension options.";
  }
  if (result.kind === "repo") {
    return "Couldn't find the repo — check the repo name in the extension options.";
  }
  return "GitHub didn't accept the file — the download is below, drag it in instead.";
}

/* Plain-words message for a failed token test. */
function tokenTestMessage(result) {
  if (!result) return "Couldn't reach GitHub — check your internet and try again.";
  if (result.kind === "auth") {
    return "That token didn't work — double-check you pasted the whole token, with nothing extra.";
  }
  if (result.kind === "repo") {
    return "The token works, but it can't see the repo — make sure the token was made for the aram-mayhem-leaderboard repo.";
  }
  return "Couldn't reach GitHub — check your internet and try again.";
}

// Export for Node tests (service worker / pages just use the globals).
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    MAYHEM_REPO,
    MAYHEM_BRANCH,
    MAYHEM_EXPORT_PATH,
    b64encodeUtf8,
    testGitHubToken,
    commitExportToGitHub,
    syncErrorMessage,
    tokenTestMessage,
  };
}
