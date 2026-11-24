# Setup checklist (Pratap)

Everything here needs your logins, so it's yours. Roughly 45 minutes, once.

## 1. Instagram + Facebook (≈10 min)
1. Create a **ScrollSmack Facebook Page** (facebook.com/pages/create).
2. In the Instagram app: Settings → Account type → switch to **Professional** (Creator or Business).
3. Link them: Instagram → Settings → Accounts Center → add the Facebook Page.

## 2. Meta app + token (≈15 min)
1. developers.facebook.com → My Apps → **Create app** → type **Business**. You're the admin; leave it in
   development mode (that's enough for your own accounts).
2. Add products **Instagram Graph API** and **Facebook Login for Business**.
3. Graph API Explorer → pick the app → **Get User Access Token** with: `instagram_basic`,
   `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `publish_video`.
4. Exchange it for a long-lived user token (Access Token Debugger → "Extend"), then call
   `GET /me/accounts` with it. The `access_token` next to the ScrollSmack Page is a **Page token that doesn't
   expire**. Note the Page `id` too.
5. `GET /<page-id>?fields=instagram_business_account` gives the **Instagram user id**.

## 3. Other keys (≈5 min)
- **Pexels**: pexels.com/api → free key.
- **Gemini**: you already have one (`~/.claude/.env`).
- **Telegram**: reuse the social-engine bot token and your chat id, or make a new bot with @BotFather.

## 4. GitHub repo (≈10 min)
1. Create a **public** repo `marketing-engine` under `pratapkumar1928` (empty, no README).
2. Push: `git remote add origin https://github.com/pratapkumar1928/marketing-engine.git && git push -u origin main`.
3. Settings → Code security → enable **Secret scanning** and **Push protection**.
4. Settings → Secrets and variables → Actions → **Secrets**, add:
   `GEMINI_API_KEY`, `PEXELS_API_KEY`, `SCROLLSMACK_META_PAGE_TOKEN`, `SCROLLSMACK_IG_USER_ID`,
   `SCROLLSMACK_FB_PAGE_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
5. Same page → **Variables**: `DRY_RUN` = `1`.

## 5. Test, then go live
1. Actions → **run** → Run workflow with `dry_run=1`. Expect a green run, a ledger commit by `engine-bot`,
   and a `videos-…` artifact. Watch a couple of the MP4s. Let the schedule run in dry mode for 2 days.
2. Actions → **report** → Run workflow. Expect a Telegram message.
3. One live test: Run workflow with `dry_run=0` while a slot is due. Expect one Reel on Instagram and on
   Facebook, with their links in the ledger and the report.
4. After the Instinct AI queue ends (Dec 4): set the `DRY_RUN` variable to `0`. Posting is now fully automatic.

## Stopping it
- Commit an empty `PAUSE` file at the repo root, or set `DRY_RUN` back to `1`.
- To turn off one platform for one app: `enabled: false` in `apps/<app>/app.yaml`.
