# Marketing engine — design

Date: 2026-11-24. Owner: Pratap. Status: draft for approval.

## Why

Pratap builds free apps (ScrollSmack first, more coming) with no revenue and no marketing budget.
ScrollSmack's bottleneck is reach: 568 Play impressions → 26 installs in its first month, and the
maker channels (X, Product Hunt, directories) brought ~no installs. Short-form video is the
channel chosen in `scrollsmack/docs/launch/promotion-plan.md`. Posting today is 1/day, done by
hand via a third party (Instinct AI) from a fixed 16-video queue ending Dec 4.

He wants **his own marketing engine**: one system that makes and posts short vertical videos for
any of his apps, **5–10 posts per day**, with **zero human touches**, at **$0/month**.

## Design principle: everything that moves is swappable

AI models, free tools and platform APIs change monthly. Pratap wants to switch any moving part
without a rewrite, and to scale to many apps. So:

- **Every external dependency sits behind one small slot**, one file per provider, chosen in
  `config.yaml` by name. The slots are `llm` (Gemini today; Claude, OpenAI or a local model are
  one file each), `video_understanding` (Gemini today), `research` sources, `broll` (Pexels),
  `music`, `renderer` (HyperFrames today), and `publishers` (one per platform).
- **Each slot is a plain function contract**, the same pattern as `social-engine`'s
  `sources/<name>.py` → `fetch()`. Examples: `llm.generate(prompt, schema) -> dict`,
  `publish(video_path, caption, env) -> Published`, `render(recipe, assets, out_path)`. No plugin
  framework and no class hierarchies.
- **Model names, prompts and thresholds live in config/prompt files, never in code.** Upgrading to
  a newer model is a one-line config change. Prompts are versioned files under `prompts/`.
- **Formats are data (recipes), not code**, so new trends never need new code.
- **Apps are data** (`apps/<app>/`), so a new app needs no code.
- **Adding a provider = one file + one config line.** The README documents each slot's contract,
  so a future Claude session can add one without reading the whole engine.

## Goals

- Generate fresh 9:16 videos daily from each app's own assets and copy, with no repeats.
- Publish them automatically to Instagram Reels, Facebook Reels, YouTube Shorts and TikTok.
- Plug in a new app by adding one folder (brand, footage, facts, copy, accounts, quotas). No code change.
- Run entirely on free infrastructure, unattended, and survive Pratap's PC being off.

## Non-goals (v1)

- Comment replies, DMs, follows, likes — all automated engagement. (Banned by the platforms; the
  same rule as `social-engine`.)
- Analytics-driven format selection. v1 logs post IDs; a later version can pull metrics.
- Merging with `social-engine` (text posts to X/Threads/Bluesky, approval-gated by design).
- New Google Flow / Veo clips. Credits can't sustain this volume and Veo 3.1 leaves Flow Dec 5.
  Existing clips are inputs; new generative footage is out.

## Anti-goals (a failure even if it works)

- Any post that misstates what an app does, invents a feature, or invents a roast line.
- Getting an account restricted or banned (spam / unoriginal-content strikes).
- Anything that breaks platform terms: no browser-automation posting, no logging in as a user.
- A monthly bill. API usage with a free tier (Gemini, Pexels) is fine; subscriptions are not.
- Touching the `gridbot` VM (e2-micro, 1 GB RAM, already swapping, runs live trading bots).

## Constraints

- **Hosting:** GitHub Actions in a **public** repo (unlimited free minutes). Secrets in GitHub
  Actions secrets, never in the repo. Everything else in the repo is public, including footage
  and copy — fine, it is all marketing material.
- **Rendering:** HyperFrames, pinned `hyperframes@0.8.106` (same as `scrollsmack/store/*`), on the
  Ubuntu runner with its preinstalled Chrome.
- **Publishing, all through each platform's own free API:**

  | Platform | API | Gate |
  |---|---|---|
  | Instagram Reels | Graph API content publishing | Business/Creator account linked to a FB Page; Meta app in dev mode is enough for accounts with a role on the app. Live day one. |
  | Facebook Reels | Graph API Page video_reels | Same Meta app + Page. Live day one. **Prerequisite (Pratap):** create a ScrollSmack Facebook Page, switch the Instagram account to Professional (Creator or Business), and link the two. |
  | YouTube Shorts | Data API v3 `videos.insert` | Uploads are private until Google's API compliance audit passes. Quota 10,000 units/day = ~6 uploads/day per project. OAuth consent screen must be "In production" or refresh tokens die after 7 days. |
  | TikTok | Content Posting API (Direct Post) | Posts are private (SELF_ONLY) until TikTok's audit passes. May be refused. |

- **Until an audit passes**, that platform is disabled in config (not "post privately") and its
  renders are kept as GitHub Actions artifacts so nothing is lost. Turning it on is a config flip.
- **Copy rules (all apps):** no profanity; no "download now"/hard CTA in captions; no claims beyond
  the app's `facts.yaml`; the joke is about the behavior, never the viewer's body, money or
  relationships. ScrollSmack roast lines are used **verbatim** from `scrollsmack`'s `strings.xml`.
- **Safe zone:** burned-in text and key UI out of the bottom 20% and right 12% of the frame;
  captions at 65–72% of frame height.

## Approaches considered

1. **Paid scheduler (Postiz Cloud / Blotato, ~$29/mo) + weekly render on PC.** Least code, and
   TikTok works without an audit. Rejected: Pratap can't spend $29/mo on unpaid projects, and it
   doesn't become his own engine.
2. **Run on the `gridbot` VM.** Already paid for. Rejected: e2-micro with ~460 MB free and 459 MB
   in swap; a headless Chrome render (1–2 GB) would starve the live trading bots. Upgrading costs
   ~$25/mo.
3. **Pratap's PC + Windows Task Scheduler.** Free, simplest. Rejected: posting stops whenever the
   PC is off.
4. **GitHub Actions, public repo, platform APIs directly — chosen.** $0, unattended, no machine
   to keep alive, and a public build-in-public repo fits his X presence. Cost: we own four
   publisher integrations, and TikTok/YouTube wait on audits.

**Turning trend research into videos** (Pratap picked 1):
1. **Recipe-driven template — chosen.** Research outputs structured recipes, and one renderer
   draws them from fixed blocks. New trends are data, so this is fully automatic and safe.
2. AI writes brand-new HyperFrames templates per trend. Rejected: unreviewed generated code fails
   in ways automatic checks miss (bad layout, misplaced text), and it is much more to build.
3. Research steers hooks and topics only. Rejected: formats go stale.

## The design

### Repo: `marketing-engine` (public, `pratapkumar1928/marketing-engine`)

```
config.yaml        which provider fills each slot + model names (the "switchboard")
prompts/           versioned prompt files (copywriter, claim checker, video breakdown, recipe synth)
engine/            Python stages: research → plan → write → render → publish → report
  llm/ research/ broll/ music/ renderer/ publishers/   one file per provider (slots)
renderer/          the HyperFrames recipe-renderer template + shared fonts/sfx
apps/<app>/
  app.yaml         name, store URL + UTM base, brand tokens, platforms on/off, target posts/day, slots
  facts.yaml       true statements about the app (the only claims copy may make)
  copy/            style.md (voice + house rules), roasts.yaml (verbatim), hashtags, niche keywords
  recipes/         seed + researched recipes (JSON)
  blocks/          app-specific HTML partials (e.g. ScrollSmack's roast overlay)
  footage/         the app's own clips (screen recordings, raw Flow clips)
research/<app>/<date>.json   weekly trend breakdowns
state/<app>/ledger.jsonl     one line per post: date, recipe, combo key, platform, post id, status
.github/workflows/daily.yml  publish-due every 30 min + morning render
.github/workflows/research.yml  weekly
```

### Daily run (one workflow, cron, plus manual `workflow_dispatch`)

1. **Plan.** For each app in `apps/` with posting enabled: pick today's N videos (N from
   `app.yaml`, default 5). Each video = format × hook × content (roast line / fact) × b-roll ×
   music, chosen so no combo key repeats the ledger and no format runs twice in a row.
2. **Write copy (AI, decided by Pratap).** The `llm` slot writes each video's hook, on-screen
   text and caption from the app's `facts.yaml`, `copy/style.md` (voice and house rules) and the
   chosen recipe. Roast lines are never generated; they come verbatim from `copy/roasts.yaml`. Each
   output passes automatic checks before use: length per platform, banned-word list, hashtag count
   3–5, no near-duplicate of a ledger caption, and a second `llm` call acting as a **claim
   checker**: "list every factual claim about the app; is each supported by facts.yaml?" Any
   failure triggers one regeneration. A second failure drops that video, not the run.
3. **Render.** Fill the format's template, `hyperframes check` (must pass — a failed check drops
   that video, not the run), `hyperframes render` → MP4 H.264/yuv420p 1080×1920.
4. **Publish.** At each slot in `app.yaml` (posts spread across the day — see scheduling), send
   the video to every enabled platform. Write the ledger line as `publishing` **before** the
   network call; a post-creating call with an unknown outcome is never retried automatically
   (same rule as `social-engine`). Final ledger update is committed back to the repo.
5. **Report.** One Telegram message per day (notification only, no buttons): what posted where,
   what failed. Reuses the existing Telegram bot token pattern from `social-engine`.

**Combo key** = format + content item + hook (b-roll and music don't count). One video
cross-posted to four platforms is one combo. *(Builder-check call.)*

**Roast lines** are copied into `apps/scrollsmack/copy/roasts.yaml` by a local sync script that
parses `scrollsmack/app/src/main/res/values/strings.xml`. The `scrollsmack` repo is private, so the
public workflow never reads it directly and needs no cross-repo token. *(Builder-check call.)*

### Scheduling

GitHub's cron is best-effort (runs can start minutes late or be skipped at peak). One morning run
renders the day's batch and uploads it as a workflow artifact; a light cron every 30 min publishes
any slot that is due and not yet in the ledger. A slot more than 2 h late is skipped, never
burst-posted.

### Trend research → recipes (weekly, decided by Pratap: option 1)

A weekly workflow researches what is working in each app's niche and turns it into **recipes**.

- **Sources (each a `research/<name>.py` slot):**
  - `youtube_shorts`: Data API search on the app's niche keywords, published in the last 14 days,
    ranked by views. Use a **separate Google Cloud project** from the uploader so research
    searches (100 units each) never eat the ~6/day upload quota.
  - `instagram_hashtags`: Graph API hashtag top media for the app's hashtags (limit: 30 unique
    hashtags per 7 days per account). Needs the Facebook Page (Pratap is creating it).
  - TikTok is **excluded**: there is no non-academic trend API, and scraping Creative Center breaks
    its terms.
- **Analysis:** the `video_understanding` slot (Gemini, which reads public YouTube URLs directly)
  breaks each top video into structure: hook type, beat list with durations, text-on-screen
  style, where the payoff lands, and length. Results are saved to `research/<app>/<date>.json`,
  committed so the history is public and diffable.
- **Recipe synthesis:** the `llm` slot clusters the breakdowns into 1–3 new recipes per week.
- **What is borrowed:** structure, pacing and hook patterns only. Never footage, audio, captions or
  creator names.

**A recipe** is a validated JSON file, `apps/<app>/recipes/<id>.json`, giving the length and an
ordered list of beats. Each beat is one of a fixed set of blocks: `hook_text`, `text_beat`,
`broll`, `app_clip`, `app_overlay` (for ScrollSmack, the roast overlay), `fact`, `end_card`. Each
beat has a duration, a text slot or source, and a transition from a fixed list. One HyperFrames
template, the **recipe renderer**, knows how to draw every block in any app's brand tokens.

Recipe gates, all automatic: the schema is valid, total length is 7–30 s, at least one block
shows the app, the safe zone is respected, and a test render passes `hyperframes check`. A new
recipe enters rotation at low weight (10% of slots). Once metrics exist (a later version), its
weight follows performance. A recipe that fails to render twice is retired.

The three v1 formats below are the **seed recipes**, written by hand.

### Formats for ScrollSmack v1 (seed recipes, all from existing material)

1. **Roast card** — hook over b-roll of someone scrolling → overlay rebuild with a verbatim roast
   line + the phrase being typed → end card. (40 lines × hooks × b-roll.)
2. **Clip remix** — one of the existing Flow clips (`promo-personas`, `promo-facetime`,
   `promo-skits`) with a new hook and end card. Rate-limited: each clip at most once per 14 days
   per platform.
3. **Fact card** — kinetic typography of one `facts.yaml` statement ("No internet permission. Not
   even one.") over b-roll → end card.

**Where blocks live:** generic blocks are in the engine's recipe renderer. An app-specific block
(ScrollSmack's `app_overlay`) is an HTML partial in `apps/<app>/blocks/`, which the renderer
includes by name. A new app with a special visual adds a partial, not engine code.

Clip remix uses the **raw** Flow clips (`promo-personas/clips/*.mp4`, `promo-facetime` /
`promo-skits` `assets/footage/`), which have no burned-in captions or end cards.

B-roll: Pexels API (free key), searched per format by a per-app keyword list, downloaded at run
time, not committed. Music: synthesized by the engine (the same approach as
`scrollsmack/store/promo-explainer/make_bgm.py`), so there are no licensing questions. Bundled
HyperFrames SFX only. *(Builder-check call.)*

### Account-safety rails

- Per-platform daily cap in `app.yaml` (target 5; hard ceiling 10 in code). **Ramp:** a newly
  enabled platform starts at 2/day and adds 1/day each week until it reaches the target. This
  lowers the risk of spam flags on young accounts. *(Builder-check call; Pratap can override.)*
- Two consecutive failures from a platform → that platform auto-pauses for the app and the daily
  report says so. A committed `PAUSE` file at repo root stops everything.
- Never post the same rendered file twice to the same platform.

### Platform audits (part of the build)

The engine's own public repo, a privacy-policy page and a demo recording are what TikTok and
Google ask for. The build prepares both applications; Pratap submits them (they need his login).

### Rollout

1. `DRY_RUN=1` default: plan + render + log, no posting. Run for 2 days, inspect artifacts.
2. Instagram + Facebook live. Start after the Instinct AI queue ends Dec 4.
3. YouTube and TikTok switch on as their audits pass.

## Left to the builder

Module layout inside `engine/`, Python version, test framework, template internals, how the
ledger commit avoids races between runs (e.g. workflow `concurrency` group), token refresh
mechanics per platform, Pexels query wording, exact report wording.
