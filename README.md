# NFL Model Board

Three spread models (Elo, Elo + QB, Blend + EPA) with key-number pricing, injury flags, and an automatic news feed from ESPN and NFL insiders on X. GitHub runs it on a schedule and republishes the board as a web page.

## One-time setup (about 20 minutes)

### 1. Put the code on GitHub
1. Create a free account at github.com if you don't have one.
2. Click **New repository**, name it `nfl-board`, and create it.
3. On the new repo page, click **uploading an existing file** and drag in everything from this folder (including the hidden `.github` folder; on a Mac press Cmd+Shift+. in Finder to see it). Commit.

### 2. Let the workflow save its results
Settings > Actions > General > Workflow permissions > **Read and write permissions** > Save.

### 3. Turn on the web page
Settings > Pages > Source: **Deploy from a branch**, Branch: **main**, folder **/docs** > Save.
Your board will be at `https://<your-username>.github.io/nfl-board/` after the first run.

Note: on a free GitHub plan the page is public to anyone who has the link. It contains no personal info, but don't share the link if you'd rather keep it private.

### 4. Add your keys (both optional, both recommended)
Settings > Secrets and variables > Actions > **New repository secret**:

| Name | What it does | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude reads each news item and tags team, player, status, and any QB change. Without it, simple keyword rules are used. | Anthropic's developer console (linked from docs.claude.com). Cost is small since only new items are read. |
| `X_BEARER_TOKEN` | Pulls posts from the insiders listed in `pipeline/config.py`. | See "Connecting X" below. |

### 5. First run
Actions tab > **Update NFL board** > **Run workflow**. It takes about 3 minutes. After that it runs on its own.

## Connecting X
A regular X account can't use the API by itself; you need developer access on top of it.
1. Sign in with your X account at the X Developer Console (start from docs.x.com).
2. Create a project and app.
3. Buy a small amount of credits and **set a monthly spending cap** (for example $25). Reads cost about $0.005 per post.
4. Copy the app's **Bearer Token** into the `X_BEARER_TOKEN` secret.

The pipeline remembers the newest post it has seen, so each post is only paid for once. `X_MAX_POSTS_PER_RUN` in `config.py` is a second safety cap.

## Schedule
Every morning, Wednesday to Friday afternoons (injury reports), Monday and Thursday before prime time, and every 20 minutes on Sunday from 10am to 3:40pm Eastern to catch inactives. Edit the `cron` lines in `.github/workflows/update.yml` to change it.

## How news affects the model
- A **confirmed** report that someone will start at QB replaces the listed starter and recomputes the Elo + QB and Blend lines. The game shows a red note saying so.
- A confirmed report that the listed QB is out, with no replacement named, shows a red warning but doesn't change the line.
- Other news is attached to the relevant games and shown in the feed. It is not priced into the lines.
- To turn off automatic QB changes, set `AUTO_QB_OVERRIDE = False` in `pipeline/config.py`.

## If something breaks
Each source is independent: if ESPN changes its unofficial endpoints or X is down, that source is skipped and the board still builds. Check the run log under the Actions tab; lines starting with `[news]` show what each source returned.
