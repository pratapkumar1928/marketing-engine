# Setup checklist (Pratap)

Everything here needs your logins, so it's yours. Roughly 45 minutes, once.

## 1. YouTube (≈15 min)
Uploads from an unverified Google project are public (no audit needed). Quota: 100 uploads/day.
1. console.cloud.google.com → new project `marketing-engine` → APIs & Services → enable **YouTube Data API v3**.
2. Google Auth Platform (OAuth consent screen): **External**, app name `marketing-engine`, your email as support
   contact. Data access → add scope `https://www.googleapis.com/auth/youtube.upload` (nothing else).
3. Audience → **Publish app** so it says **In production**. Don't leave it in *Testing*: test-mode refresh tokens
   die after 7 days. You don't need Google's verification for your own account; you'll just see an
   "unverified app" warning when you sign in.
4. Clients → **Create client** → type **Web application** → authorized redirect URI
   `https://developers.google.com/oauthplayground`. Copy the client ID and secret.
5. developers.google.com/oauthplayground → gear icon → tick **Use your own OAuth credentials** → paste them.
   In "Input your own scopes" enter `https://www.googleapis.com/auth/youtube.upload` → **Authorize APIs** →
   sign in as the ScrollSmack Google account and pick the ScrollSmack channel → Advanced → continue past the
   warning → **Exchange authorization code for tokens** → copy the **Refresh token**.
6. The token stops working if it goes 6 months unused, or if you revoke the app. Then redo step 5.

## 1b. TikTok inbox drafts (≈20 min, then one tap per video)
The engine can't post to TikTok by itself: TikTok only approves fully automatic posting for public apps, not
for a tool that posts to your own account. So each video arrives as a **draft in your TikTok inbox**, and a
Telegram message gives you its caption. Open TikTok → inbox notification → paste caption → Post. TikTok allows
at most **5 unfinished drafts per 24 h**: if you skip them, uploads fail, and after two failures TikTok
auto-pauses (set `platforms.tiktok.resume_after` in `app.yaml` to restart it).
1. developers.tiktok.com → log in → **Manage apps → Connect an app**. Website `https://scrollsmack.app`, privacy
   policy `https://scrollsmack.app/privacy/`, platform **Web**.
2. Add **Login Kit** with redirect URI `https://scrollsmack.app/`, and **Content Posting API** with Direct Post
   **off** (we only use Upload). Scopes: `user.info.basic`, `video.upload`.
3. **Sandbox** tab → create a sandbox → add the ScrollSmack TikTok account as a target user. Use the sandbox's
   client key/secret. If TikTok refuses uploads in the sandbox (the live test shows an error code in the
   ledger), submit the app for review instead: "posts our own app's marketing videos to our account as inbox
   drafts, which we finish in the TikTok app".
4. Put `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET` in `.env` and in GitHub secrets.
5. `.venv/Scripts/python tools/tiktok_auth.py scrollsmack`. The first time it prints a `TIKTOK_TOKEN_KEY=…` line:
   add it to `.env` **and** GitHub secrets, then run the tool again. Sign in as ScrollSmack, allow, paste back
   the address you land on (the page itself may 404; only the address matters).
6. Commit and push `state/scrollsmack/tiktok_token.enc` (encrypted). The bot refreshes and re-commits it.
   **Never run a live (`DRY_RUN=0`) post from your PC**: it would refresh the token locally and the bot's copy
   would stop working. If the report ever shows `tt token refresh failed`, redo steps 5–6.

## 2. Instagram / Facebook (not in use)
Meta disabled the ScrollSmack Instagram account on 2026-11-21 and said there's no further review. Don't create a
new account for it (Meta's terms forbid it, and a replacement risks your other Meta accounts). The publisher
code stays; to use it for another app, see git history of this file for the Page + token steps.

## 3. Other keys (≈5 min)
- **Pexels**: pexels.com/api → free key.
- **Gemini**: you already have one (`~/.claude/.env`).
- **Telegram**: reuse the social-engine bot token and your chat id, or make a new bot with @BotFather.

## 4. GitHub repo (≈10 min)
1. Create a **public** repo `marketing-engine` under `pratapkumar1928` (empty, no README).
2. Push: `git remote add origin https://github.com/pratapkumar1928/marketing-engine.git && git push -u origin main`.
3. Settings → Code security → enable **Secret scanning** and **Push protection**.
4. Settings → Secrets and variables → Actions → **Secrets**, add:
   `GEMINI_API_KEY`, `PEXELS_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`,
   `SCROLLSMACK_YOUTUBE_REFRESH_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_TOKEN_KEY`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
5. Same page → **Variables**: `DRY_RUN` = `1`.

## 5. Test, then go live
1. Actions → **run** → Run workflow with `dry_run=1`. Expect a green run, a ledger commit by `engine-bot`,
   and a `videos-…` artifact. Watch a couple of the MP4s. Let the schedule run in dry mode for 2 days.
2. Actions → **report** → Run workflow. Expect a Telegram message.
3. One live test: Run workflow with `dry_run=0` while a slot is due. Expect one public Short on the ScrollSmack
   channel, one TikTok inbox draft plus its Telegram caption message, and both in the ledger and the report.
4. After the Instinct AI queue ends (Dec 4): set the `DRY_RUN` variable to `0`. Posting is now fully automatic.

## Stopping it
- Commit an empty `PAUSE` file at the repo root, or set `DRY_RUN` back to `1`.
- To turn off one platform for one app: `enabled: false` in `apps/<app>/app.yaml`.
