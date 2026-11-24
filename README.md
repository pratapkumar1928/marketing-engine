# marketing-engine

A zero-touch, $0 short-video marketing engine for indie apps. Every 30 minutes a GitHub Actions run
checks each app's posting schedule. For any slot that's due, it picks a format ("recipe") and an item
of content, has an LLM write the hook and caption, checks every claim against the app's facts,
renders a 9:16 video with [HyperFrames](https://github.com/heygen-com/hyperframes), and posts it to
Instagram Reels and Facebook Reels. A Telegram message sums up each day.

Design: `docs/superpowers/specs/2026-11-24-marketing-engine-design.md` · Setup: `docs/setup.md` ·
New app: `docs/add-an-app.md` (or `/add-app` in Claude Code).

## How it fits together

```
config.yaml          which provider fills each slot (swap one = change a name here)
apps/<app>/          one folder per app: app.yaml, facts.yaml, copy/, recipes/, blocks/, footage/, brand/
recipes/             shared formats every app inherits
prompts/             versioned LLM prompts
engine/              schedule → plan → write → render → publish → report
state/<app>/ledger.jsonl   append-only post log (committed by the bot)
```

## Slots (swap any provider: add one file, change one line in `config.yaml`)

| Slot | Contract | Today |
|---|---|---|
| `llm` | `engine/llm/<name>.py: generate(prompt, schema, *, model) -> dict` | `gemini` |
| `broll` | `engine/broll/<name>.py: fetch(query, out_dir, *, rng) -> Path \| None` (never raises) | `pexels` |
| `music` | `engine/music/<name>.py: make_track(seconds, out, *, seed) -> Path` | `synth` (original, no licence) |
| `renderer` | `engine/renderer/<name>.py: stage_assets(...)`, `build_html(recipe, copy, content, app, srcs)`, `render(html, files, workdir, out, version)` | `hyperframes` |
| `publishers` | `engine/publishers/<name>.py: publish(video, caption, app, *, http) -> Published` (raises `PublishError`) | `instagram`, `facebook` |

## Recipes

A recipe is JSON: `{id, content: roast|fact|clip, weight, beats: [...]}`. Each beat is one of
`hook_text, text_beat, broll, app_clip, app_overlay, fact, end_card` with a `dur`, an optional
`bg` (`broll|clip|dark`), `text` (`hook|content|line:<key>`) and `transition` (`cut|fade|slide_up|punch`).
Gates: 7–30 s long, shows the app, ends with `end_card`. Shared recipes live in `recipes/`; an app's own
recipes in `apps/<app>/recipes/` override by `id`. A recipe whose content pool the app doesn't have is skipped.

## Controls

- `DRY_RUN` repo variable: anything but `0` renders and logs without posting (default).
- `PAUSE` file at the repo root: no posting at all.
- A platform auto-pauses after two failed/unknown posts in a row; set
  `platforms.<p>.resume_after: <ISO time>` in `app.yaml` to resume it.
- Ramp: a platform posts 2/day in its first week, then +1/day each week up to `target` (hard cap 10).

## Local

```
python -m venv .venv && .venv/Scripts/pip install -e .[dev]
.venv/Scripts/python -m pytest                     # fast suite
.venv/Scripts/python -m pytest -m slow             # real renders (needs Node + Chrome + ffmpeg)
DRY_RUN=1 .venv/Scripts/python -m engine.main run --now 2026-12-05T08:05-05:00
.venv/Scripts/python -m engine.main check-app scrollsmack --preview 2
```
Secrets come from `ENGINE_SECRETS` (JSON, set by Actions), the environment, or `.env` at the repo root
(never read on Actions).
