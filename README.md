# ARAM Mayhem — Team Leaderboard

This is your group's leaderboard website. It shows who is doing best
at ARAM Mayhem (the chaotic League of Legends mode you all play),
with a ranking, graphs, and tips for each player. It replaces the old
page at bboyisk.github.io/aram-mayhem-assessment, which kept getting
blocked.

**You do not need to know how to code. You do not need to know
GitHub.** This page walks you through setup one click at a time.

---

# START HERE — get your page live in about 15 minutes

## Before you start — what you need

- A computer (Windows or Mac) and an internet connection.
- An email address you can open.
- The project folder I gave you, called `aram-mayhem-leaderboard`.
  It has all the files inside already. You will not edit any of them.
- About 15 minutes. You only do this once.

## Words you will see, in plain English

GitHub uses a few special words. Here is what they mean, so nothing
on screen is scary:

- **GitHub** — a free website that stores files and can run small
  automatic jobs for you. Think of it as a folder online plus a
  robot.
- **Repository (repo)** — just a folder on GitHub. Your repo will
  hold all the leaderboard files.
- **Commit** — the green "save" button. When you upload files, you
  click Commit to save them.
- **Pages** — GitHub's free website hosting. It turns your folder
  into a real web page with an address you can share.
- **Actions** — the robot. It runs a job for you on a schedule.
- **Workflow** — one job the robot does. Ours is called "Update
  leaderboard daily".
- **Branch (main)** — the main copy of your files. You will see the
  word "main" in a dropdown. Just leave it as it is.

## Step 1 — Make a GitHub account (2 minutes)

1. Open your web browser (Chrome, Edge, Safari — any is fine) and go
   to **https://github.com**.
2. Click the **Sign up** button (top right).
3. It will ask for:
   - **Email** — type your email address, then click Continue.
   - **Password** — pick a password, then click Continue.
   - **Username** — pick a name. This name will be part of your page
     address, so pick something you are happy to share. Click
     Continue.
4. It will ask you to prove you are not a robot (a puzzle or a
   checkbox). Do that.
5. GitHub will send a code to your email. Open your email, find the
   code, type it into GitHub, and click Verify.
6. It may ask a few questions about what you will use GitHub for.
   You can click **Skip** on all of them.

You now have a GitHub account. Write down your username — you will
need it in Step 4.

## Step 2 — Make the folder for this project (2 minutes)

1. Make sure you are signed in to GitHub. Look at the top right of
   the page — you should see your profile picture or a circle with
   your first letter.
2. Click the **+** sign at the top right of the page. A small menu
   drops down. Click **New repository**.
3. You will see a form. Fill it in like this:
   - **Repository name:** type exactly this:
     `aram-mayhem-leaderboard`
   - **Description:** leave it empty.
   - **Public or Private:** click **Public**. (The free website
     hosting in Step 4 needs a public folder. Anyone with the link
     can see the leaderboard — that was already true of the old
     page.)
   - **Add a README file:** leave this box **unchecked**.
   - Leave everything else exactly as it is.
4. Click the green **Create repository** button at the bottom.

You will land on a mostly empty page that says "Quick setup". That
is normal. Ignore everything on it and go to Step 3.

## Step 3 — Upload the files (5 minutes)

1. On your empty repository page, click the **Add file** button (near
   the top right, next to a green "Code" button). A menu drops down.
   Click **Upload files**.
2. A page appears that says "Drag files here to add them to your
   repository".
3. Open the folder on your computer called
   `aram-mayhem-leaderboard` (the one I gave you). You should see
   files and folders inside it, including `index.html`,
   `players.yaml`, a `data` folder, a `scripts` folder, and a folder
   called `.github`.
4. **Drag the whole folder itself** onto the GitHub upload page.
   Click the folder called `aram-mayhem-leaderboard` **once** to
   select it, then drag **that folder** onto the page. Do NOT open
   the folder and drag the files inside it — if you do, the files
   land flat at the top level, the robot's job file ends up in the
   wrong place, and the page cannot find its data. (This is the
   most common mistake. If your Actions page later shows no
   "Update leaderboard daily" job, this is why.)
5. Wait for all the files to finish uploading. You will see a list
   of them on the page.
6. Scroll to the bottom and click the green **Commit changes**
   button. ("Commit" just means "save".)

**How to check it worked:** after the page reloads, you should see
these things listed on your repository page:

- `index.html`
- `players.yaml`
- `data` (a folder)
- `scripts` (a folder)
- `.github` (a folder)

Click on `.github`, then `workflows`. You should see a file called
`update.yml` inside. If you see all of that, you did it right.

**If you see `update.py`, `data.json`, `check_fresh.py` and
`update.yml` listed at the top level instead, with no folders:**
the upload went flat (the files were dragged, not the folder).
The quickest fix is to delete the repository and start Step 2
again: on the repository page, click **Settings**, scroll all the
way down to **Danger Zone**, click **Delete this repository**, type
the name, and confirm. Then redo Step 2 and Step 3, dragging the
whole folder this time.

**If you cannot see the `.github` folder on your computer:** it is
hidden because its name starts with a dot. That is normal.
- On a Mac: in Finder, press **Cmd + Shift + .** (period) and hidden
  folders will appear.
- On Windows: in File Explorer, click **View** at the top, then tick
  **Hidden items**.
- Then drag the files again, including `.github`.
- If it still will not upload, tell me and I will walk you through
  the other way (an app called GitHub Desktop).

## Step 4 — Turn on the website (2 minutes)

1. On your repository page, click **Settings** in the top menu
   (it is near the right, after Code, Issues, Pull requests,
   Actions, Projects).
2. A settings page opens. Look at the menu on the **left side** and
   click **Pages**.
3. You will see a section called **Build and deployment**. It has
   two dropdown boxes:
   - **Source:** leave it as "Deploy from a branch".
   - **Branch:** click the dropdown and pick **main**. Leave the
     folder box next to it as **/ (root)**.
4. Click **Save**.
5. Wait about one minute, then refresh the page (press F5, or
   Ctrl+R on Windows / Cmd+R on Mac).
6. Near the top of the page you will now see a box that says
   **"Your site is live at"** followed by a blue link. That link is
   your leaderboard's address. It looks like this, with your
   username in it:

   `https://<your-username>.github.io/aram-mayhem-leaderboard/`

7. Click the link. The leaderboard should open. Right now it shows
   the numbers from Nov 8 — that is expected. Step 5 fills in the
   fresh games.

## Step 5 — Run the updater once, right now (3 minutes)

Do not wait until midnight. Run it once by hand now, so you can see
it work.

1. Go back to your repository page (click your repository name at
   the top left to get back).
2. Click the **Actions** tab in the top menu.
3. If GitHub shows a button that says something about enabling
   workflows, click **"I understand my workflows, go ahead and
   enable them"**. (It only asks once.)
4. On the **left side** of the Actions page, you will see a list of
   jobs. Click **Update leaderboard daily**. (If it is not in the
   list at all — only "pages-build-deployment" is there — the
   upload in Step 3 went flat. See "If something looks wrong"
   below: delete the repository and redo Steps 2–3, dragging the
   whole folder.)
5. On the right side, click the **Run workflow** dropdown button.
   A small box opens. Click the green **Run workflow** button
   inside it.
6. A run appears at the top of the list, with a yellow dot next to
   it. That means it is working. Wait 1–3 minutes and refresh the
   page.
7. The yellow dot should turn into a **green checkmark**. Green
   means it worked. (A red X means it failed — see "If something
   looks wrong" below.)
8. Click on the run to open it. Click the job called **update**,
   then click **Update data**. You will probably see lines like
   `BLOCKED — PlayARAM returned 403 (Cloudflare challenge)` for
   each player. That is expected now: PlayARAM refuses requests
   from GitHub's computers (see Step 7 — the extension is how the
   fresh games get in). The run still gets a green checkmark, and
   the page keeps the Nov 8 numbers for now.
9. The numbers fill in when you do Step 7 (the extension) and
   click **Update leaderboard** once. The workflow starts by itself
   after that. Until then, the page is supposed to still say Nov 8.

## Step 6 — You are done with the website setup

That is the whole setup for the page itself. One more piece follows
in Step 7 — the extension that feeds it fresh games. From now on:

- Every night at **12:00 AM CST**, the robot runs by itself. If the
  extension sent fresh games (Step 7), it imports them, updates the
  numbers, and republishes the page. If there is no new file, it
  tries PlayARAM directly and, as expected, gets refused — the page
  simply keeps its last numbers. It tries again at 12:30 AM if the
  first try fails.
- You never have to refresh the page by hand for it to update. The
  only pasting is the one-time token in Step 7.

## Step 7 — Install the extension (the part that keeps the numbers fresh)

PlayARAM refuses requests from GitHub's computers, but it loads fine
in your own Chrome browser at home. So instead of GitHub asking
PlayARAM for the games, a tiny extension in YOUR Chrome looks at the
5 profiles the way you would — one click from you, once a day or
after a game night — and sends the games straight to the repo
itself. The robot sees the new file, imports it, and republishes
the page, all by itself. Click the button — that is it.

The extension only wakes up on PlayARAM profile pages. It never
talks to PlayARAM on its own, never tries to get past a security
check, and never refreshes constantly — it reads the pages you
already opened, at a human pace. That is why it does not look like
a bot.

### Install it (once, about 3 minutes)

1. Find the file I gave you called `aram-mayhem-extension.zip`
   and **unzip it**: on Windows, right-click it and pick
   **Extract All**, then click Extract. On a Mac, just double-click
   it. You will get a folder called `extension`.
2. In Chrome, open a new tab and go to **chrome://extensions**
   (type it in the address bar and press Enter).
3. At the top right of that page, turn on **Developer mode**
   (a small switch). Chrome may warn you that developer mode can
   be risky — this is your own extension, built for you, so it is
   fine to turn it on.
4. Click the **Load unpacked** button (top left).
5. Pick the `extension` folder from step 1 (the one with
   `manifest.json` inside it) and click Select.
6. You should now see **ARAM Mayhem Collector** in the list, with
   a black-and-gold "M" icon. Click the puzzle-piece icon in
   Chrome's toolbar (top right) and then the pin next to
   **ARAM Mayhem Collector**, so its icon stays visible.

That is the whole install. Chrome may show a small warning each
time it starts, saying it found an extension in developer mode.
That is normal for an extension installed this way — just ignore
it. (The extension is not in the Chrome store, because it is a
private tool made only for your group.)

If you already installed the first version of the extension (the
one that only downloaded a file): unzip the new zip the same way,
and when Windows or Mac asks, pick **Replace the files** so the
old `extension` folder gets the new files. Then go to
**chrome://extensions**, find **ARAM Mayhem Collector**, and click
the little circular **reload** arrow on its card. That is it — your
saved token (if you added one) stays saved.

### Add the token (once, about 5 minutes)

The extension needs one password-like key — called a token — so it
is allowed to put the file in your repo itself. You make it once on
GitHub, paste it into the extension, and then you never touch it
again until it expires (see the note at the end of this part).

1. Go to **github.com** and make sure you are signed in. Click
   your **profile photo** (top right corner) and pick **Settings**.
2. Scroll all the way down the left-hand menu and click
   **Developer settings** (near the bottom).
3. On the left, under **Personal access tokens**, click
   **Fine-grained tokens**.
4. Click the green **Generate new token** button.
5. Under **Token name**, type `ARAM Mayhem extension`.
6. Under **Expiration**, pick **1 year**. (GitHub will email you
   before it expires. When that happens, just make a new one the
   same way and paste it in again — everything else stays the
   same.)
7. Under **Repository access**, pick **Only select repositories**,
   then click the box and pick **aram-mayhem-leaderboard**.
8. Scroll down to **Repository permissions**. Find **Contents** in
   the list, click the dropdown next to it, and pick **Read and
   write**. (This is the permission that lets the extension put
   the file in the repo. It cannot do anything else.)
9. Scroll to the bottom and click the green **Generate new token**
   button.
10. GitHub shows you the token — a long jumble of letters and
    numbers. Click the **copy button** next to it (the little
    two-squares icon). **Copy it now: GitHub only shows it once,
    and if you close this page without copying it, you have to
    start over.**
11. Go back to Chrome. Click the **ARAM Mayhem Collector** icon in
    the toolbar, then click **Extension options** at the bottom of
    the little box. (Or go to **chrome://extensions**, find
    **ARAM Mayhem Collector**, and click **Details** → **Extension
    options**.)
12. Paste the token into the **GitHub token** box and click
    **Save**, then click **Test**. If it says the token works,
    you are done. If it says the token did not work, check you
    pasted the whole thing, with nothing extra before or after it.

**Keep the token secret, like a password.** It can only write to
this one repo, but never share it and never paste it in a chat, an
email, or anywhere else. You can take it away any time: GitHub →
your photo → Settings → Developer settings → Personal access
tokens → find "ARAM Mayhem extension" → Delete. If you do that,
the extension just goes back to downloading the file, and you drag
it in as below.

### Use it (one click, once a day or after a game night)

1. Click the **ARAM Mayhem Collector** icon in Chrome's toolbar.
   A small box opens. Click the big **Update leaderboard** button.
2. Chrome will open each of the 5 profiles, one at a time, and
   read the games — about 1–2 minutes for all 5. **Do not close
   the tabs it opens**, and do not click around in them while it
   works. You can watch it go, or just let it run.
3. When it finishes, the box says "Synced — the page rebuilds
   itself, give it a minute." That is the whole job. Wait about a
   minute, reload your leaderboard link (Ctrl+Shift+R on Windows,
   Cmd+Shift+R on Mac), and the top should say "Last updated"
   with today's date. The per-game rows, the "what to work on"
   tips, and the top 3 / worst 3 champions should be filled in.

That is it. No file to drag, no workflow to run. The robot starts
itself the moment the extension puts the file in the repo.

### If you have not added a token yet (the drag-a-file way)

This still works, exactly as before:

1. Click **Update leaderboard** as above. When it finishes, the
   box says "Done" and Chrome downloads one file called
   `mayhem-extension-export-YYYY-MM-DD.json` (the date is today's
   date). It lands in your Downloads folder.
2. **Rename that file to `extension-export.json`.** (Right-click it
   in Downloads, pick Rename, type the new name.)
3. Go to your repo on GitHub, click the **`data`** folder, then
   **Add file** → **Upload files**, and drag the renamed file in.
   Scroll down and click the green **Commit changes** button.
   (If GitHub says the file already exists, click **Commit changes**
   anyway — it replaces the old one. That is supposed to happen.)
4. Putting that file in the repo starts the robot by itself now —
   you do not have to run the workflow by hand. Wait 1–2 minutes
   for the green checkmark on the Actions page, then reload the
   leaderboard link. (The robot also runs every night at 12:00 AM
   and picks the file up then, if you would rather wait.)

### If the extension box says something is wrong

- **"Waiting for verification" / "verify you are human".**
  PlayARAM showed its security checkbox on one of the profiles.
  The extension stopped and left the tab open on purpose — it
  never tries to solve that check itself. Click the checkbox on
  the PlayARAM tab, then press **Update leaderboard** again.
- **It found 0 games for someone.** The profile page probably did
  not load properly. Check your internet, wait a minute, and press
  the button again. If it keeps happening, tell me which player
  it was.
- **"The token didn't work."** The token in the extension options
  is wrong or expired. Open the options (click the extension icon
  → **Extension options**), paste a fresh token (make one as in
  "Add the token" above), click **Save**, then **Test**. Until it
  works, the extension downloads the file instead — use the
  drag-a-file way above.
- **"Couldn't find the repo."** The token was made for a different
  repo, or the wrong repo was picked in step 7 of "Add the token".
  Make a new token and pick **aram-mayhem-leaderboard** under
  "Only select repositories".
- **"GitHub didn't accept the file."** Something went wrong on
  GitHub's side. The file was downloaded instead — drag it in as
  in "If you have not added a token yet" above. If it keeps
  happening, tell me what the box said.
- **The button does nothing.** Close the little box and click the
  icon again. If it still does nothing, the extension may have
  been turned off: go to chrome://extensions and check that
  **ARAM Mayhem Collector** is switched on.
- **The page still shows Nov 8 after the workflow run.** If you
  dragged the file in yourself, check that it is named exactly
  `extension-export.json` and is inside the `data` folder — not
  in the top level of the repo, and not still called
  `mayhem-extension-export-....json`. If the name is wrong, the
  robot does not see it.

## How do I know it worked? (checklist)

You are done when you can tick all of these:

- [ ] Your leaderboard link opens and shows the 5 players.
- [ ] You installed the extension (Step 7), added the token, and
      clicked Update leaderboard once — the box said "Synced".
- [ ] The line at the top says "Last updated" with today's date
      (after clicking Update leaderboard once).
- [ ] The Actions page shows a run with a green checkmark.
- [ ] The "What to work on" box under each player has tips in it
      (not "fills on the first daily run").

If all four are ticked, you are finished. Send your friends the link.

## If something looks wrong

Find what you see below, and do what it says.

- **The Actions page has no "Update leaderboard daily" job.**
  The upload in Step 3 went flat: the files were dragged instead of
  the whole folder, so GitHub never saw the `.github` folder that
  holds the robot's job. Check the **Code** tab — if you see
  `update.py`, `data.json` and `update.yml` listed at the top level
  with no folders, that is the problem. Delete the repository
  (Settings → scroll to **Danger Zone** → **Delete this repository**)
  and redo Steps 2–3, dragging the **whole folder** this time.

- **The link shows "404 — page not found."**
  The website is not turned on yet, or it picked the wrong folder.
  Go to Settings → Pages and check: Branch is `main`, folder is
  `/ (root)`. Click Save, wait one minute, reload the link.

- **The Actions run has a red X.**
  Click into the failed run, click the **update** job, and read the
  last few lines under "Update data":
  - *"PlayARAM returned no usable page / blocked"* — PlayARAM
    refused the request from GitHub's computers. This is expected
    and is not a problem: the page keeps the last numbers it had
    and says so at the top. The fresh games come from the
    extension (Step 7), not from this request. If you have not
    installed the extension yet, that is the fix.
  - *"0 ARAM Mayhem games"* — PlayARAM answered but showed no
    Mayhem games for someone. Usually a Riot ID is mistyped. Check
    the names in `players.yaml` — they should be exactly
    i3i3oy#NA1, CreamiNataella#NA1, PikabUwU#NA1,
    Vincent Chan#NA1, Ohwutahel#NA1.

- **The run is green but the page still shows Nov 8.**
  Your browser is showing you an old saved copy. Do a hard reload:
  hold Ctrl and press F5 (Windows) or hold Cmd+Shift and press R
  (Mac). If it still says Nov 8, check the "Last updated" line — a
  green run that found 0 new games just means nobody played since
  the snapshot, which is fine.

- **The workflow run is green but nothing changed, and the page
  still says the numbers are old.**
  The robot probably did not see your file. Check that it is
  named exactly `extension-export.json` and sits inside the
  `data` folder. If you uploaded it with its downloaded name
  (`mayhem-extension-export-....json`), rename it and upload it
  again. If the file was broken (for example, the download was
  interrupted), the robot moves it aside as
  `extension-export-failed-<date>.json` and writes a note on the
  page — just run the extension again and upload the new file.

- **The page says the data is more than 48 hours old.**
  The nightly updates have not worked for 2 days. Go to the Actions
  tab and look for red X marks. If you see them, tell me what the
  last lines of the failed run say and I will help you fix it.

- **You get stuck on any step.**
  Tell me which step you are on and what you see on your screen
  (you can describe it or send a screenshot). Do not guess — I would
  rather walk you through it than have you click the wrong thing.

---

# Details, if you are curious (you can skip all of this)

## Where the data comes from

**No Riot API key is needed.** Riot's own API does not give out ARAM
Mayhem games, so asking Riot for a key would not help. The data comes
from PlayARAM.gg, a website that shows ARAM and ARAM Mayhem match
history when you type in a Riot ID. It is the same source the original
page used.

- The numbers on the page right now are a snapshot from **Nov 8,
  2026**, copied from the original page. That page got its numbers
  from PlayARAM (each player's last 100 Mayhem games) plus MayhemMeta
  for population averages. The per-game rows, the "what to work on"
  tips, and the top/worst champions are empty until the first update
  run — nothing was made up to fill them.
- **The fresh games come from the Chrome extension (Step 7).**
  It runs in your own browser, on your home internet, and reads
  the 5 profiles the way you would — one click from you, once a
  day or after a game night. It also opens each game's Details
  panel, so it brings back the damage numbers the server fetch
  could not see, and it clicks "Load more" until it has all 50
  games. With a token saved, it puts the file in `data/` as
  `extension-export.json` itself, and the robot imports it right
  away. Without a token, it downloads the file and you drag it
  into `data/` yourself (same file, same name).
- The updater still tries PlayARAM directly once a day from
  GitHub's computers, as a backup. PlayARAM refuses those requests
  (Cloudflare), so that try fails quietly and the page keeps its
  last numbers — that is expected, not an error.
- PlayARAM shows only the latest **20 games** per profile visit to
  an automated fetch, so the updater keeps a saved list (a cache)
  of games it has already seen and adds the new ones each day. The
  extension clicks "Load more" in your browser, so one extension
  run brings back all 50 games at once and the window fills
  immediately. Nothing is made up to fill the gap.
- PlayARAM's match list shows result, champion, KDA, CS and the
  Mayhem event stats (including skillshots dodged), but **not**
  damage dealt/taken in the list itself — that lives in each game's
  Details panel, which the extension opens for you. So games from
  the extension usually have damage (Output and Damage Taken join
  the grade), and games from the server fetch do not (those two stay
  blank — a missing field is skipped, never scored as 0). Turret
  takedowns are not shown per player anywhere, so there is no
  structures criterion in the rating at all.
- If PlayARAM ever refuses the request, the updater keeps the last
  numbers it had, writes a note about it on the page, and tries again
  at 12:30 AM. It never erases the leaderboard.

## How the ranking works (plain words)

The point of the ranking is: who is doing best, judged on everything,
not on one stat, and not skewed by the role they play.

- **Role first — judged from the game, not just the champion.** Every
  part of the score is compared only against players who played the
  same role in that game — Damage (carries), Frontline (tanks and
  fighters), or Support. The role comes from the champion plus the
  augments taken and the items built: Malphite built AP counts as
  Damage, Seraphine built with enchanter items counts as Support.
  A tank with 8 kills can score higher than a carry with 12 kills,
  because the tank is being compared to other tanks. Raw kills never
  compare a tank to a carry. If a game has no augments or items
  recorded, it falls back to the champion's usual role.
- **Champion second.** Each part also compares you against other
  people playing the same champion (70% role, 30% same champion).
  Playing a champion well *for that champion* counts.
- **Whole performance, not one stat.** One game is graded on the
  criteria the data source provides for it. From PlayARAM that is
  KDA Efficiency, Teamplay, Death Quality, Augments and Mechanics
  (skillshots dodged); Output
  (damage dealt) and Damage Taken join in when the extension has
  read the game's Details panel in your browser. Output is your
  share of the team's damage dealt when all five teammates' damage
  is known for the match (games where the whole group queued
  together), otherwise damage per minute; Damage Taken is the same
  idea for damage you soaked, judged within your role — a tank
  soaking damage is compared with other tanks, never with a carry's
  damage taken. Teamplay is kill participation — your kills +
  assists divided by team kills — and team kills come from the five
  group members' games for the same match, so it only has a value
  on full-stack games where everyone queued together. (The page
  also shows each player's kill participation % and deaths per
  game, averaged over the window; both stay blank when the data
  is not available, never 0.) PlayARAM's own match list does not show damage, so
  games from a server fetch have no damage and those two criteria
  stay blank for them. Mechanics (skillshots dodged
  per minute) is the 7th graded criterion, blended as a percentile
  within role like the others — a good dodger scores high even on a
  tank. KDA is only 1 of the
  graded criteria, and winning is only 15% of the final score.
- **Steady beats one great game.** The final score is 55% average
  grade + 20% middle grade + 10% worst-quarter grade + 15% win rate.
  One pop-off game cannot carry a rank; a low floor pulls it down.
- **"What to work on" comes only from the last 20 games.** Each
  player's pros, cons and tips are computed from their OWN most
  recent 20 games: their graded criteria are ranked by their
  recent-20 subscore, so the strongest are the pros and the
  weakest are the cons, each with a tip tied to that criterion
  and the player's own number — different players get different
  tips because their strongest and weakest areas differ. Nothing
  from older games or the Nov 8 snapshot goes into it. The tips also split games
  played **with 2 or more of the group** versus **solo games**, so
  stacked and solo play do not get mixed up.
- **Top 3 / worst 3 champions** at the bottom are per player, from
  the last 50 games, 2 or more games on that champion (one game is
  not a pattern), with games, win-loss, win rate, grade, and a
  one-sentence reason. Each champion shows its official portrait
  in a little round bubble. A champion in the top 3 never appears
  in the worst 3.
- **Fun titles** under each player's name are earned fresh every
  run from that window's stats — never fixed to a name, so they
  move when gameplay changes. At most one title per player, in
  this order: **The Untouchable** (best KDA *and* fewest deaths
  per game — both, or no title that run), **The Glass Cannon**
  (most damage per minute, else biggest share of the group's
  damage), **The Glue** (highest kill participation), **The
  Matrix** (most skillshots dodged per minute), **The Lone Wolf**
  (lowest kill participation, assigned last so nobody who earned
  a better title gets stuck with it). A title whose deciding stat
  is blank for everyone that run (damage is blank until the
  extension reads it) is left off rather than guessed. Each title
  comes with a one-line summary from the player's own numbers.
  Pronouns: she/her for CreamiNataella and PikabUwU; names or
  they/them for everyone else, never he/him.
- **The role maps come from the game's own data.** Item roles come
  from Data Dragon item tags (tank items carry Health with Armor or
  Magic Resist, AP items carry ability power, and so on), and the
  enchanter and support-quest items are listed by name. If a patch
  renames an item or changes its tags, the maps in
  `scripts/update.py` and `extension/parser.js` need regenerating
  from the new Data Dragon files — the two copies must stay
  identical, or the same game would get a different role depending
  on which side read it.

Worked example (Nov 8 snapshot): Ohwutahel plays mostly tanks,
Vincent Chan plays all carry champs. Vincent ranks 2nd (55.4) and
Ohwutahel 4th (47.9) — not because carries get more kills.
Ohwutahel's tank games grade 52.4, close to Vincent's level; his
overall rank is pulled down by the games where he played off-role,
not by playing tanks.

## What is in each file (plain words)

| File | What it is |
|---|---|
| `index.html` | The whole web page: leaderboard, graphs, player cards, tips, top/worst champions. It only reads a data file — it never calls any game website. |
| `data/data.json` | All the numbers the page shows. Seeded from the Nov 8 snapshot. |
| `players.yaml` | The 5 players and their Riot IDs (all NA, Mayhem only), and the 50-game window. |
| `scripts/update.py` | The robot's instructions: fetch the games, compute the scores, save the numbers. |
| `scripts/check_fresh.py` | A check that runs after each update: if the numbers are older than 3 days, it fails the run on purpose so GitHub emails you. |
| `.github/workflows/update.yml` | The schedule: run the updater every night at 12:00 AM CST, retry at 12:30 AM — and also whenever the extension puts a fresh export in `data/`. |
| `extension/` | The Chrome extension (Step 7): reads the 5 profiles in your browser and sends the games straight to the repo (or downloads one file if no token is saved). It comes as a separate zip, `aram-mayhem-extension.zip`. |
| `data/extension-export.json` | The file the extension sends to the `data` folder (itself, with a token — or you upload the downloaded file, renamed). The robot imports it and removes it. It is not in the repo by default. |
| `data/manual_games.csv` | A blank form for the manual backup (see below). |

## Manual backup (only if PlayARAM stops working)

If PlayARAM refuses the automatic requests for days, you can fill in
the games by hand:

1. Open PlayARAM.gg in your own browser and look up each player's
   Riot ID.
2. Copy their recent Mayhem games into `data/manual_games.csv`
   (the column names are in the first row of the file).
3. Upload the file to the repo the same way as in Step 3, or tell me
   and I will help.

A person copying their own history in a browser is not what gets
anyone blocked. This is a backup only — you should never need it
week to week.

## Honest limits

- **The extension needs one click from you.** It is not fully
  automatic on purpose — the click is what makes it look like you
  browsing, which is what keeps it working. If PlayARAM changes
  how its profile pages look, the extension may stop reading them
  properly until it is updated — tell me if it suddenly finds
  0 games and I will fix it.
- **The token expires.** If you picked 1 year, GitHub emails you
  before it runs out. Make a new one the same way (Step 7) and
  paste it into the extension options — everything else stays
  the same. While the token is expired, the extension just
  downloads the file instead, so nothing breaks.
- **PlayARAM is a small third-party site.** It sits behind a service
  called Cloudflare, which sometimes refuses automated requests (a
  403 error or a cut connection). I saw that happen from one computer
  while building this, while a normal browser loads it fine. The
  updater asks politely, retries, and never erases anything — but if
  PlayARAM keeps refusing GitHub's computers, the manual backup above
  is the answer.
- **The Nov 8 snapshot is last-100 games, not last-50.** The scores
  (I3i3oy 56.1, Vincent Chan 55.4, CreamiNataella 55.0, Ohwutahel
  47.9, PikabUwU 47.5) were computed on last-100 games, so the first
  last-50 run may move scores a little.
- **Population win rates come from MayhemMeta** (mayhemmeta.com),
  which does not say where its data comes from — treat those as
  background context, not part of the score, exactly as the original
  page did.
- **Mashbrains was removed** (Nov 8): he does not play Mayhem with
  the group, so he is out of the data, the player list, and the page
  entirely.

## Still needed from you

1. **Your GitHub username** — only so I can check the page address
   with you. Or just follow the steps above yourself; I cannot push
   to GitHub without your account.
2. **Who is who** (optional): which display name is you / your
   husband, so the player cards can say so. I did not guess.

The 5 players, confirmed Nov 8, all NA, Mayhem only: i3i3oy#NA1,
CreamiNataella#NA1, PikabUwU#NA1, Vincent Chan#NA1, Ohwutahel#NA1.
