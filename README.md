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
   then click **Update data**. You should see lines like
   `20 games on profile, 20 new, cache now 20` for each player on
   the first run (PlayARAM shows 20 games at a time, so the first
   run finds 20; later runs find fewer new ones). That means it
   found your games.
9. Now go back to your leaderboard link from Step 4 and reload the
   page (Ctrl+Shift+R on Windows, Cmd+Shift+R on Mac, so your
   browser does not show you an old saved copy). The line at the
   very top should now say **"Last updated"** with today's date and
   time. The per-game rows, the "what to work on" tips, and the top
   3 / worst 3 champions should now be filled in.

## Step 6 — You are done

That is the whole setup. From now on:

- Every night at **12:00 AM CST**, the robot runs by itself, fetches
  the new games, updates the numbers, and republishes the page. It
  tries again at 12:30 AM if the first try fails.
- You never have to open GitHub again, unless the page tells you
  something is wrong (see below).
- You never have to refresh the page by hand for it to update, and
  you never have to paste anything anywhere.

## How do I know it worked? (checklist)

You are done when you can tick all of these:

- [ ] Your leaderboard link opens and shows the 5 players.
- [ ] The line at the top says "Last updated" with today's date.
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
    refused the request from GitHub's computers. The page keeps the
    last numbers it had and says so at the top. Wait for the 12:30
    AM retry. If it keeps failing for several days, tell me — the
    backup is copying the games by hand from PlayARAM into a file
    (see "Manual backup" below).
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
- After setup, the updater asks PlayARAM for each player's Mayhem
  history **once a day** — 5 quiet requests, not hundreds, and never
  when someone refreshes the page. That is why this version cannot get
  blocked the way the old one did.
- PlayARAM shows only the latest **20 games** per profile visit, so
  the updater keeps a saved list (a cache) of games it has already
  seen and adds the new ones each day. The last-50 window fills over
  the first few daily runs — the first run scores on 20 games per
  player, then 40, then 50. Nothing is made up to fill the gap.
- PlayARAM's match list shows result, champion, KDA, CS and the
  Mayhem event stats (including skillshots dodged), but **not**
  damage dealt/taken or turret takedowns. So Output and Conversion
  stay blank on PlayARAM games — the grade uses the criteria that
  are there (KDA, teamplay, death quality, augments), and a missing
  field is skipped, never scored as 0.
- If PlayARAM ever refuses the request, the updater keeps the last
  numbers it had, writes a note about it on the page, and tries again
  at 12:30 AM. It never erases the leaderboard.

## How the ranking works (plain words)

The point of the ranking is: who is doing best, judged on everything,
not on one stat, and not skewed by the role they play.

- **Role first.** Every part of the score is compared only against
  players in the same role — Damage (carries), Frontline (tanks and
  fighters), or Support. A tank with 8 kills can score higher than a
  carry with 12 kills, because the tank is being compared to other
  tanks. Raw kills never compare a tank to a carry.
- **Champion second.** Each part also compares you against other
  people playing the same champion (70% role, 30% same champion).
  Playing a champion well *for that champion* counts.
- **Whole performance, not one stat.** One game is graded on the
  criteria the data source provides for it. From PlayARAM that is
  KDA Efficiency, Teamplay, Death Quality and Augments; Output and
  Conversion join in only when damage / turret data exists (a manual
  CSV). Mechanics (skillshots dodged) is shown but not blended into
  the grade. KDA is only 1 of the graded criteria, and winning
  is only 15% of the final score.
- **Steady beats one great game.** The final score is 55% average
  grade + 20% middle grade + 10% worst-quarter grade + 15% win rate.
  One pop-off game cannot carry a rank; a low floor pulls it down.
- **"What to work on" comes only from the last 20 games.** Each
  player's tips are computed from their most recent 20 games,
  compared with the group's recent-20 averages. Nothing from older
  games or the Nov 8 snapshot goes into it. The tips also split games
  played **with 2 or more of the group** versus **solo games**, so
  stacked and solo play do not get mixed up.
- **Top 3 / worst 3 champions** at the bottom are per player, from
  the last 50 games, 3 or more games on that champion only, with
  games, win-loss, win rate, grade, and a one-sentence reason. Each
  champion shows its official portrait in a little round bubble.
  If a player has only a few champions with 3+ games, the same
  champion can appear in both lists.

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
| `.github/workflows/update.yml` | The schedule: run the updater every night at 12:00 AM CST, retry at 12:30 AM. |
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
