# marketing-engine

Zero-touch short-video marketing for Pratap's apps (ScrollSmack first). Public repo, GitHub Actions, $0/month.
Publishing: **YouTube Shorts + TikTok inbox drafts** for now. Meta disabled the ScrollSmack Instagram on 2026-11-21 (no appeal): don't
recreate it; the instagram/facebook publishers stay but are off.
Spec: `docs/superpowers/specs/2026-11-24-marketing-engine-design.md`. Plan 1 (core):
`docs/superpowers/plans/2026-11-24-marketing-engine-core.md`. Plans 2 (trend research → recipes) and
3 (YouTube + TikTok + audits) are not built yet.

## Rules that are easy to break
- **The `publishing` ledger line is written (fsync'd) before any post-creating network call.** Never reorder it.
- **A `publishing` line older than 30 min with no outcome becomes `unknown` and is never re-posted.** The
  daily report says "CHECK MANUALLY". Don't add auto-retry for post-creating calls (`creates_post=True` in
  `publishers/meta_http.call`): only `ConnectTimeout` / 429 count as retryable there, and even those are
  not retried in the same run.
- **In CI the `publishing` line is also pushed before the post** (`Deps.checkpoint` → `engine/gitsync.py`,
  on when `LEDGER_PUSH=1`). If the push fails, the post is skipped and logged `failed`: a post the remote
  ledger doesn't know about would be re-posted by the next run, whose checkout comes from the remote.
- `run.yml` checks out `ref: github.ref_name` (the branch tip), not the queued `github.sha`: a run that waited
  in the concurrency queue must see the previous run's ledger. `state/**/ledger.jsonl` merges by `union`.
- `run --now <ISO>` is always a dry run (pretend slot ids are never posted). A manual dispatch with `now`, or one
  forcing `dry_run=1` while the repo is live, does not commit the ledger, so tests never use up real slots.
  A `dry_run=0` dispatch does commit: real posts are always recorded.
- Shell lines in workflows never contain `${{ }}`: pass values through `env:` (script-injection rule).
- Duplicate-caption checks compare `caption_text` (no hashtags), not `caption`.
- The renderer's `npx` subprocess gets an **allowlisted** environment (`_ENV_ALLOW` + `HYPERFRAMES_/NODE_/NPM_CONFIG_/
  XDG_/PUPPETEER_` prefixes in `renderer/hyperframes.py`): it runs third-party npm code. If a render breaks on a new
  machine, add the missing variable there, never pass `os.environ` wholesale.
- **A slot is planned, dropped or posted at most once.** A dropped slot (copy rejected, render failed) is
  logged per platform so later runs don't retry it.
- **Missed slots are skipped, never burst-posted** (`late_skip_minutes`, 120).
- **The repo is public.** Secrets only in GitHub Actions secrets (`ENGINE_SECRETS` = `toJSON(secrets)`).
  No secret in any log, error or exception: every client re-raises `type(e).__name__` only, `from None`.
  Tokens go in headers (`x-goog-api-key`, `Authorization: OAuth …`), never URLs, except Telegram's (path) and
  Pixabay's (query param, the only way it accepts one), whose errors are swallowed the same way.
- B-roll is **Pixabay** (Pexels paused new API keys, Nov 2026). Pixabay has few portrait clips: it prefers them,
  else takes the sharpest landscape one, which `object-fit: cover` crops to 9:16. `.env` is read only from the repo root and never on Actions.
- Workflows: `schedule` + `workflow_dispatch` only. GitHub drops most `*/30` crons, so the gridbot VM's `me-tick.timer`
  dispatches `run.yml` with `dry_run=auto` every 30 min (`deploy/vm-tick/`; token = Actions-only PAT, never Contents). **Never `pull_request_target`.** Every `uses:` is pinned to a
  full SHA. Only `run.yml` has `contents: write` (ledger commit).
- **Roast lines are verbatim from ScrollSmack's `strings.xml`** via `tools/sync_roasts.py` → `copy/roasts.yaml`.
  Never generated, never edited by hand. The renderer reads them from the content item, not from AI copy.
- **AI copy may only claim what `facts.yaml` says.** `copywriter.check_claims` fails closed on any malformed
  checker reply. Copy with non-Latin letters, markdown headings, `<`/`>` or banned phrases is rejected.
- **Safe zone:** all burned-in text inside `SAFE_BOX` (x 80–950, y 220–1536). App overlay partials must
  respect it too (ScrollSmack's panel is 870 px wide for this reason).
- **YouTube** (`publishers/youtube.py`): refresh token → resumable upload. Unverified Google projects upload public
  (Google changed this; the spec's "private until audit" is outdated). The OAuth app must be *In production* or
  refresh tokens die in 7 days. `containsSyntheticMedia: true` on every upload (clip remixes are AI footage).
- **TikTok** (`publishers/tiktok.py`) uploads **inbox drafts** (scope `video.upload`); Pratap taps to post and pastes
  the caption from a Telegram message (inbox uploads can't carry one). Max 5 pending drafts per 24 h. Direct Post
  is out: TikTok's audit excludes tools for your own accounts, and unaudited posts are private-only.
- **TikTok refresh tokens rotate** (the old one dies on use), so they live Fernet-encrypted in
  `state/<app>/tiktok_token.enc` (key: `TIKTOK_TOKEN_KEY` secret), not in a GitHub secret. Refresh only near
  expiry; save to disk and push (`gitsync`) **before** using the new token. Never refresh from a local run.
  First token / re-auth: `tools/tiktok_auth.py <app>`.
- GSAP comes from jsDelivr with an SRI hash in `renderer/base.html.tpl`; bumping GSAP means recomputing it.
- The renderer retries once with `--experimental-fast-capture=false` (known HyperFrames + system Chrome fix).
- GitHub disables scheduled workflows in public repos after 60 days without activity. The bot's ledger
  commits keep it alive, but after a long `PAUSE`, check the Actions tab for "workflow disabled".

## Adding things
- Provider: one file in the slot's folder + its name in `config.yaml` (contracts in README).
- App: `/add-app` skill or `docs/add-an-app.md`; validate with `python -m engine.main check-app <name> --preview 3`.
- Recipe: JSON in `recipes/` (shared) or `apps/<app>/recipes/`; must pass `engine.recipes.validate_recipe`.

## Run
- Tests: `.venv/Scripts/python -m pytest` (fast), `-m slow` (real HyperFrames renders, ~4 min; set
  `HYPERFRAMES_BROWSER_PATH` to system Chrome on Windows).
- Local dry run: `DRY_RUN=1 python -m engine.main run --now <ISO>`. Delete `state/` afterwards: it's real ledger data.
