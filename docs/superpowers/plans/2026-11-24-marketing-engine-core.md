# Marketing Engine Core (Plan 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A zero-touch engine on GitHub Actions that, for each app folder, plans, AI-writes, renders and posts N short videos a day to Instagram Reels and Facebook Reels, starting with ScrollSmack.

**Architecture:** Python stages (schedule → plan → write → render → publish → report) driven by a 30-minute cron. Each due slot is handled **just in time**: plan, write, render and post one video in the same run. Every external dependency is a one-file "slot" chosen by name in `config.yaml`. Apps, recipes and prompts are data. State is an append-only JSONL ledger committed back to the repo.

**Tech Stack:** Python 3.12, `requests`, `PyYAML`, `jsonschema`, `tzdata`, `pytest`; Node 22 + `hyperframes@0.8.106` (npx) for rendering; Gemini REST API; Pexels API; Meta Graph API v21.0+; Telegram Bot API; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-24-marketing-engine-design.md`

**Scope:** This is plan 1 of 3. Plan 2 = weekly trend research → recipes. Plan 3 = YouTube + TikTok publishers and audit applications. Out of scope here: anything under `research/`, `youtube`, `tiktok`.

**Deviation from spec (simplification, flag to Pratap):** the spec has a morning render plus artifact hand-off to a 30-min publisher. This plan renders each video **in the run that posts it**. Same behaviour, no artifact passing between runs. The cost is ~2 min of runner time per post, which is free on a public repo.

## Global Constraints

- Cost: $0/month. Free API tiers only (Gemini key already owned, Pexels free key). No paid services.
- Never touch the `gridbot` VM.
- Renderer pinned: `npx --yes hyperframes@0.8.106`. Output: MP4, H.264, yuv420p, 1080×1920.
- Safe zone: no burned-in text or key UI in the bottom 20% (y > 1536px) or right 12% (x > 950px). Captions sit at 65–72% height (1250–1380px top).
- Copy rules: no profanity; no "download now" / hard CTA in captions; no claim not in the app's `facts.yaml`; jokes target the behaviour, never body, money or relationships. ScrollSmack roast lines are verbatim from `strings.xml`, never generated.
- Caption: max 300 chars, 3–5 hashtags taken only from the app's `copy/hashtags.yaml`. Hook: max 60 chars.
- Daily cap per platform: `target` from `app.yaml` (default 5), hard ceiling 10 in code. Ramp: 2/day for the first week a platform is enabled, then +1/day per week up to `target`.
- A slot more than 2 h late is skipped, never burst-posted.
- Ledger `publishing` line is written and committed to disk **before** the network call. A post-creating call with an unknown outcome is never auto-retried.
- Two consecutive failures for (app, platform) → that platform auto-pauses for that app. A `PAUSE` file at the repo root stops all posting.
- Secrets: only from GitHub Actions secrets (env `ENGINE_SECRETS`, JSON) or a local `.env`. Never in logs, errors or exceptions. Clients re-raise as `type(e).__name__` only, `from None`.
- Workflows: `schedule` and `workflow_dispatch` only, never `pull_request_target`. Actions pinned to full commit SHAs. `permissions: contents: write` only on the job that commits the ledger.
- `DRY_RUN` defaults ON (`DRY_RUN=1`). Only `DRY_RUN=0` posts.
- Commit messages: no `Co-Authored-By` trailer (Pratap's rule).

## Review Focus

1. **Overlapping or duplicated cron runs** (GitHub fires late, or twice) must never double-post a slot. Owned by Task 11: `test_second_run_same_slot_does_not_publish`.
2. **A run dies between `publishing` and the result.** The next run must mark it `unknown`, report it, and never re-post. Task 11: `test_stale_publishing_becomes_unknown_not_retried`.
3. **Gemini returns malformed JSON or an unsupported claim twice.** Only that video is dropped; later slots still run. Task 6: `test_two_failures_raise_copy_rejected`; Task 11: `test_copy_rejected_drops_slot_continues`.
4. **Pexels returns nothing usable or is down.** The video still renders on the dark background; b-roll never drops a video. Task 8: `test_pexels_no_portrait_returns_none`; Task 9: `test_missing_broll_uses_dark_bg`.
5. **Content pool exhausted inside the cooldown** (5/day burns ~70 items per 14 days). The planner reuses the least-recently-used item instead of stalling. Task 5: `test_exhausted_pool_picks_lru`.

---

## File Structure

```
pyproject.toml  .gitignore  config.yaml  README.md  CLAUDE.md
prompts/copywriter.md  prompts/claim_checker.md
engine/
  types.py        Slot, Plan, Copy, Published, PublishError, CopyRejected
  config.py       load_config, load_app, list_apps, secret
  ledger.py       append, read, last_status, recent
  schedule.py     daily_cap, slots_for_day, due_slots
  recipes.py      load_recipes, validate_recipe (schema in recipe.schema.json)
  planner.py      plan_slot
  copywriter.py   write_copy, validate_copy, check_claims
  llm/gemini.py   generate
  broll/pexels.py fetch
  music/synth.py  make_track
  renderer/hyperframes.py  build_html, render
  publishers/instagram.py  publish
  publishers/facebook.py   publish
  report.py       build_report, send
  main.py         CLI: run | report | check-app
  checkapp.py     check_app
renderer/         template assets: base.html.tpl, fonts/, sfx/
recipes/          shared recipes every app inherits (fact_card, problem_app)
.claude/skills/add-app/SKILL.md   onboarding skill for a new app
apps/scrollsmack/ app.yaml facts.yaml copy/{style.md,hashtags.yaml,roasts.yaml,keywords.yaml}
                  recipes/*.json blocks/app_overlay.html brand/{icon.png} footage/{clips.yaml,*.mp4}
tools/sync_roasts.py
state/scrollsmack/ledger.jsonl
.github/workflows/run.yml  .github/workflows/report.yml
tests/  (one test file per engine module, tests/fixtures/)
```

---

### Task 1: Scaffold, config and secrets

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config.yaml`, `engine/__init__.py`, `engine/types.py`, `engine/config.py`
- Test: `tests/test_config.py`, `tests/fixtures/apps/demo/app.yaml`

**Interfaces:**
- Produces:
  - `engine/types.py`: dataclasses `Slot(app: str, slot_id: str, at: datetime, platforms: list[str])` (slot_id = `"YYYY-MM-DD#i"`), `Plan(slot: Slot, recipe_id: str, content_id: str, combo: str)`, `Copy(hook: str, texts: dict[str, str], caption: str, hashtags: list[str])`, `Published(platform: str, post_id: str, url: str)`; exceptions `PublishError(msg, retryable: bool)` and `CopyRejected(reason: str)`.
  - `load_config(root: Path) -> dict` (parses `config.yaml`).
  - `list_apps(root: Path) -> list[str]` (folder names under `apps/` that contain `app.yaml`).
  - `load_app(root: Path, name: str) -> dict` (parsed `app.yaml` with `dir` added as a Path).
  - `secret(name: str) -> str`: reads `ENGINE_SECRETS` (JSON object) first, then `os.environ`, then `.env` at the root. Raises `KeyError(name)` (the name only) if missing.

- [ ] **Step 1: Write failing tests**

```python
def test_list_apps_finds_folders_with_app_yaml(tmp_root): assert list_apps(tmp_root) == ["demo"]
def test_secret_prefers_engine_secrets(monkeypatch):
    monkeypatch.setenv("ENGINE_SECRETS", '{"X":"a"}'); monkeypatch.setenv("X","b"); assert secret("X") == "a"
def test_secret_missing_raises_keyerror_with_name_only(monkeypatch):
    with pytest.raises(KeyError) as e: secret("NOPE")
    assert e.value.args == ("NOPE",)
def test_config_names_providers(root): assert load_config(root)["llm"]["provider"] == "gemini"
```

- [ ] **Step 2: Run `pytest tests/test_config.py -v`.** Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** `pyproject.toml` deps: `requests`, `PyYAML`, `jsonschema`, `tzdata`; dev: `pytest`. `.gitignore`: `.env*`, `out/`, `cache/`, `__pycache__/`, `.venv/`, `node_modules/`. `config.yaml`:

```yaml
llm: {provider: gemini, model: gemini-3.8-flash}   # same default as social-engine
broll: {provider: pexels}
music: {provider: synth}
renderer: {provider: hyperframes, version: "0.8.106"}
publishers: [instagram, facebook]
hard_cap_per_platform: 10
late_skip_minutes: 120
```
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: scaffold, config and secret lookup`.

---

### Task 2: Ledger

**Files:** Create `engine/ledger.py`; Test `tests/test_ledger.py`

**Interfaces:**
- Produces:
  - `append(path: Path, event: dict) -> None`: adds `ts` (UTC ISO), writes one JSON line, `flush` + `os.fsync` before returning.
  - `read(path: Path) -> list[dict]` (missing file → `[]`; a corrupt trailing line is skipped).
  - `last_status(events, slot_id: str, platform: str) -> str | None` (the latest `event` value for that pair).
  - `recent(events, field: str, n: int) -> list` (last n non-null values of a field).
- Event names: `planned`, `publishing`, `published`, `failed`, `unknown`, `dry_run`, `dropped`. Fields: `app, slot_id, platform, event, recipe, combo, caption, post_id, url, error`.

- [ ] **Step 1: Tests:** `test_append_then_read_roundtrip`, `test_last_status_returns_latest`, `test_corrupt_last_line_ignored` (write `'{"a":1}\n{"bro'` → read returns 1 event).
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: append-only ledger`.

---

### Task 3: Schedule (caps, ramp, due slots)

**Files:** Create `engine/schedule.py`; Test `tests/test_schedule.py`

**Interfaces:**
- Consumes: `Slot` (Task 1), `last_status` (Task 2).
- `app.yaml` shape used here:
```yaml
timezone: America/New_York
post_times: ["08:00","10:00","12:00","13:30","15:00","17:00","18:30","19:30","20:30","22:00"]
platforms:
  instagram: {enabled: true, enabled_on: 2026-12-05, target: 5}
  facebook:  {enabled: true, enabled_on: 2026-12-05, target: 5}
```
- Produces:
  - `daily_cap(p: dict, day: date, hard_cap: int) -> int`: 0 if disabled or before `enabled_on`; else `min(target, hard_cap, 2 + weeks_since_enabled)`.
  - `slots_for_day(app: dict, day: date, hard_cap: int) -> list[Slot]`: n = max cap over platforms. Slot times are n entries of `post_times` spread evenly, index `round(i*len/n)`. Platform p takes the slots at the evenly spread indices of its own cap within n. Times are tz-aware in the app's timezone.
  - `due_slots(app, now: datetime, events, hard_cap, late_min) -> list[Slot]`: today's slots with `at <= now`, `now - at <= late_min`, keeping only platforms whose `last_status` is `None`.

- [ ] **Step 1: Tests**
```python
def test_ramp(): p={"enabled":True,"enabled_on":date(2026,12,5),"target":5}
    assert [daily_cap(p, date(2026,12,5)+timedelta(weeks=w),10) for w in range(5)] == [2,3,4,5,5]
def test_disabled_or_future_is_zero(): ...  # == 0
def test_hard_cap_wins(): target 50 → 10 after many weeks
def test_slots_spread_and_platform_subsets(): caps ig=4, fb=2 → 4 slots; fb in exactly 2, spread (not the first two)
def test_late_slot_skipped(): slot 08:00, now 10:01 → not due
def test_already_logged_platform_not_due(): events has publishing for (slot,"instagram") → only facebook due
def test_dst_day_has_correct_local_times(): day 2027-03-14 → first slot is 08:00 America/New_York
```
- [ ] **Step 2: Run → FAIL. Step 3: Implement (`zoneinfo.ZoneInfo`). Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: slot scheduling with ramp and late skip`.

---

### Task 4: Recipe schema, gates and seed recipes

**Files:** Create `engine/recipe.schema.json`, `engine/recipes.py`, `recipes/{fact_card,problem_app}.json` (shared, every app inherits), `apps/scrollsmack/recipes/{roast_card,clip_remix}.json` (app-only); Test `tests/test_recipes.py`

**Interfaces:**
- Recipe JSON: `{"id": str, "content": "roast"|"fact"|"clip", "weight": number>0, "beats": [Beat...]}`. Beat: `{"block": "hook_text"|"text_beat"|"broll"|"app_clip"|"app_overlay"|"fact"|"end_card", "dur": number, "bg": "broll"|"clip"|"dark" (optional), "text": "hook"|"content"|"line:<key>" (optional), "transition": "cut"|"fade"|"slide_up"|"punch" (optional, default cut)}`. `app_clip` with `dur: "clip"` means use the clip's own length, capped at 8 s.
- Produces:
  - `load_recipes(root: Path, app: dict) -> list[dict]`: shared `root/recipes/*.json` merged with `apps/<app>/recipes/*.json`; an app recipe with the same `id` overrides the shared one. Keeps only recipes that pass validation (the invalid ones are logged by id) **and** whose content pool is non-empty for this app. A `clip` recipe is dropped for an app with no `footage/clips.yaml`; a `roast` recipe is dropped for an app with no `copy/roasts.yaml`. So a brand-new app with only `facts.yaml` gets exactly the shared fact-based recipes.
  - `validate_recipe(r: dict, clip_max: float = 8.0) -> list[str]` (empty = valid). Gates from the spec: schema valid; total 7–30 s (count `"clip"` durations as `clip_max`); contains at least one of `app_clip | app_overlay | fact`; the last beat is `end_card`.
- Seed recipes (exact beats):
  - `roast_card`: hook_text 2.6 bg broll text hook → app_overlay 4.2 text content (punch) → end_card 1.8
  - `clip_remix`: app_clip "clip" text hook → end_card 1.8
  - `fact_card` (shared): hook_text 2.2 bg broll → fact 3.6 bg broll text content (slide_up) → end_card 2.0
  - `problem_app` (shared, content `fact`): hook_text 2.4 bg broll → text_beat 2.4 bg broll text `line:problem` → fact 3.0 bg dark text content (punch) → end_card 2.0

- [ ] **Step 1: Tests:** `test_seeds_valid`, `test_too_short_rejected` (total 5 s), `test_no_app_block_rejected`, `test_must_end_with_end_card`, `test_unknown_block_rejected`, `test_app_recipe_overrides_shared_by_id`, `test_facts_only_app_gets_only_fact_recipes` (fixture app with only `facts.yaml` → ids == {"fact_card","problem_app"}).
- [ ] **Step 2: Run → FAIL. Step 3: Implement with `jsonschema.Draft202012Validator`. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: recipe schema, gates, seed recipes`.

---

### Task 5: Planner

**Files:** Create `engine/planner.py`; Test `tests/test_planner.py`

**Interfaces:**
- Consumes: `load_recipes` (Task 4), ledger events (Task 2), `Slot`/`Plan` (Task 1).
- Content pools (Task 7 provides the files): `roast` → `copy/roasts.yaml` items `{id, persona, headline, subtitle}`; `fact` → `facts.yaml` items `{id, text}`; `clip` → `footage/clips.yaml` items `{id, file, dur, desc}`.
- Produces: `plan_slot(slot: Slot, app: dict, recipes: list[dict], events: list[dict], rng: random.Random, cooldown_days: int = 14) -> Plan`.
  - Recipe: weighted choice, excluding the recipe used in the previous planned slot for this app.
  - Content: random among items whose combo `f"{recipe_id}:{content_id}"` wasn't planned in the last `cooldown_days`. If none remain, pick the **least recently used** item.

- [ ] **Step 1: Tests:** `test_no_same_recipe_twice_in_a_row`, `test_respects_cooldown`, `test_exhausted_pool_picks_lru` (every item used; the oldest is chosen), `test_deterministic_with_seeded_rng`.
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: slot planner with cooldown and LRU fallback`.

---

### Task 6: LLM slot + copywriter + checks

**Files:** Create `engine/llm/__init__.py`, `engine/llm/gemini.py`, `engine/copywriter.py`, `prompts/copywriter.md`, `prompts/claim_checker.md`; Test `tests/test_copywriter.py`, `tests/test_gemini.py`

**Interfaces:**
- Produces:
  - `engine.llm.get(cfg: dict) -> Callable[[str, dict], dict]`: imports `engine.llm.<provider>` by name. This is the slot pattern; reuse it for every slot.
  - `gemini.generate(prompt: str, schema: dict, *, model: str, http=requests) -> dict`: POST `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, with the key in the `x-goog-api-key` header (**never** in the URL), `generationConfig.responseMimeType="application/json"` and `responseSchema=schema`. Parse the first candidate's text as JSON. Errors re-raised as `RuntimeError(type(e).__name__)` from None.
  - `write_copy(plan: Plan, recipe: dict, app: dict, content: dict, llm, recent_captions: list[str]) -> Copy`: renders `prompts/copywriter.md` with the app facts, `style.md`, hashtag list, recipe beats and content item. Calls `llm(prompt, COPY_SCHEMA)`. Runs `validate_copy` and `check_claims`. On failure, regenerates once with the failure reasons appended. On a second failure, raises `CopyRejected`.
  - `validate_copy(c: Copy, app: dict, recent_captions) -> list[str]`: hook ≤ 60; caption ≤ 300; 3–5 hashtags, all in `hashtags.yaml`; no banned word (global list in `copywriter.py` plus `app.yaml: banned`), matched case-insensitively on word boundaries; `difflib.SequenceMatcher` ratio ≥ 0.8 against any recent caption → duplicate.
  - `check_claims(c: Copy, facts: list[str], llm) -> list[str]`: calls `llm(claim_checker_prompt, {"claims":[{"text":str,"supported":bool}]})` and returns the unsupported claim texts.
  - `texts` keys: `"hook"` plus one key per beat `text: line:<key>`. The roast `content` is never in `texts`; the renderer reads it verbatim from the content item.

- [ ] **Step 1: Tests (the fake llm is a lambda returning canned dicts)**
```python
def test_valid_copy_passes(): ...
def test_hashtag_not_in_list_rejected(): ...
def test_banned_word_rejected(): caption "Download now ..." → reason mentions "download now"
def test_near_duplicate_rejected(): ...
def test_unsupported_claim_triggers_one_retry_then_ok(): llm call count == 4 (copy, check, copy, check)
def test_two_failures_raise_copy_rejected(): ...
def test_malformed_llm_json_counts_as_failure(): llm raises ValueError twice → CopyRejected
def test_gemini_key_in_header_not_url(): fake http records the call; key not in url
def test_gemini_error_hides_key(): http raises ConnectionError("...KEY...") → str(err) has no key
```
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Prompts are plain Markdown with `{placeholders}` filled by `str.format_map`. The copywriter prompt includes the global copy rules verbatim. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: llm slot, copywriter, claim checker`.

---

### Task 7: ScrollSmack app folder and roast sync

**Files:** Create `tools/sync_roasts.py`, `apps/scrollsmack/{app.yaml,facts.yaml}`, `apps/scrollsmack/copy/{style.md,hashtags.yaml,keywords.yaml,roasts.yaml}`, `apps/scrollsmack/blocks/app_overlay.html`, `apps/scrollsmack/brand/icon.png`, `apps/scrollsmack/footage/{clips.yaml,*.mp4}`, `renderer/fonts/*`, `renderer/sfx/impact.mp3`; Test `tests/test_sync_roasts.py`, `tests/test_app_scrollsmack.py`

**Interfaces:**
- Produces: `sync_roasts.parse(strings_xml: str) -> list[dict]` (`{id: f"{persona}-{i}", persona: <persona_* display name>, headline, subtitle}`, paired by index from `roast_<p>_headline` / `roast_<p>`). CLI: `python tools/sync_roasts.py <path-to-strings.xml>` writes `copy/roasts.yaml`.
- Sources (local machine, copy in):
  - strings: `C:/AI/Claude Project/scrollsmack/app/src/main/res/values/strings.xml`
  - fonts/sfx: `scrollsmack/store/promo-pov/assets/{fonts,sfx}`
  - icon: `scrollsmack/store/ic_play_512.png`
  - overlay markup: port the `ov` HTML and `ov_js` from `scrollsmack/store/promo-pov/build_pov.py` into `blocks/app_overlay.html`, with `{{persona}} {{headline}} {{subtitle}}` placeholders and a `<script data-at>` snippet that uses `{{t}}` for its start time
  - clips: `promo-personas/clips/{grandma,mom,gym_bro,narrator,ex,bestie,court_partner,standard}.mp4`, `promo-facetime/assets/footage/{grandma_take1,mom_take2,ex_take1}.mp4`, `promo-skits/assets/footage/{chef,workout,couple}_main.mp4`. Each file must be < 100 MB; check with `du`.
- `facts.yaml` (copy these facts, true per `scrollsmack/CLAUDE.md`): free on Google Play, Android only; no internet permission; no account; nothing leaves the phone (backup off); 8 roast personas; dismiss by typing "I am wasting my time"; pick which apps to watch; set your own limit; the overlay yields if you leave the app; pause 1 hour / until 7 AM.
- `app.yaml`: store URL `https://play.google.com/store/apps/details?id=com.scrollsmack.app`, bio link base `https://scrollsmack.app/?utm_source={platform}`, brand tokens (`#000000`, `#FF2D2D`, `#FFD400`, `#FFB4AB`, fonts Archivo Black / JetBrains Mono), schedule block as in Task 3, and `meta: {ig_user_id_secret: SCROLLSMACK_IG_USER_ID, page_id_secret: SCROLLSMACK_FB_PAGE_ID, token_secret: SCROLLSMACK_META_PAGE_TOKEN}`.
- `style.md`: the voice (playful tough love, deadpan, short) and the Global Constraints copy rules.

- [ ] **Step 1: Tests:** `test_parse_pairs_8_personas_40_lines` (fixture = the real strings.xml copied to `tests/fixtures/strings.xml`), `test_scrollsmack_app_loads_and_recipes_valid`, `test_every_clip_file_exists_and_listed`.
- [ ] **Step 2: Run → FAIL. Step 3: Build the folder and run `python tools/sync_roasts.py "C:/AI/Claude Project/scrollsmack/app/src/main/res/values/strings.xml"`. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: scrollsmack app folder and roast sync`.

---

### Task 8: B-roll and music slots

**Files:** Create `engine/broll/{__init__,pexels}.py`, `engine/music/{__init__,synth}.py`; Test `tests/test_broll.py`, `tests/test_music.py`

**Interfaces:**
- Produces:
  - `pexels.fetch(query: str, out_dir: Path, *, rng, http=requests, min_dur: float = 3.0) -> Path | None`: GET `https://api.pexels.com/videos/search?query=&orientation=portrait&per_page=15` with header `Authorization: <PEXELS_API_KEY>`. Pick a random video with `duration >= min_dur`, choose its file with height ≥ 1920 (else the tallest portrait file), download, return the path. Any error or no match → `None` (logged as a type name only).
  - `synth.make_track(seconds: float, out: Path, *, seed: int) -> Path`: a WAV bed. Port `scrollsmack/store/promo-explainer/make_bgm.py` (stdlib only) and vary tempo/key from the seed.
  - Slot getters `engine.broll.get(cfg)` / `engine.music.get(cfg)`, using the same pattern as `engine.llm.get`.

- [ ] **Step 1: Tests:** `test_pexels_picks_portrait_hd` (fake http JSON), `test_pexels_no_portrait_returns_none`, `test_pexels_http_error_returns_none`, `test_synth_writes_wav_of_length` (`wave` module: frames/rate ≈ seconds ± 0.05).
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: pexels b-roll and synth music slots`.

---

### Task 9: Recipe renderer

**Files:** Create `renderer/base.html.tpl`, `renderer/hyperframes.json`, `renderer/package.json` (copy from promo-pov, pinned `0.8.106`), `engine/renderer/{__init__,hyperframes}.py`; Test `tests/test_renderer.py`

**Interfaces:**
- Consumes: Plan, Copy, recipe, content item, app (Tasks 1–7), b-roll path or None, music path.
- Produces:
  - `build_html(recipe, copy: Copy, content: dict, app: dict, assets: dict[str, str]) -> str`: a single composition `data-composition-id="main"`, 1080×1920, GSAP timeline registered on `window.__timelines["main"]`, the structure used in `promo-pov`. One Python function per block (`block_hook_text`, `block_text_beat`, `block_broll`, `block_app_clip`, `block_app_overlay`, `block_fact`, `block_end_card`), each `(beat, t0, ctx) -> (html, js)`. `app_overlay` loads `apps/<app>/blocks/app_overlay.html` and fills placeholders from the content item **verbatim** (HTML-escaped). All text containers sit inside the safe box `left:80px; top:220px; width:870px; height:1316px` (exposed as the constant `SAFE_BOX`). The end card shows the icon, app name, `facts.yaml`'s first fact and "Free on Google Play". `bg: broll` with a missing b-roll falls back to dark (`#000`).
  - `render(html: str, assets: dict, workdir: Path, out: Path, version: str) -> Path`: copy `renderer/` into `workdir`, write `index.html`, copy assets into `workdir/assets/`, run `npx --yes hyperframes@{version} check` (non-zero → `RuntimeError("check failed")` with stdout tail), then `render`. Locate the produced MP4 (run `npx hyperframes@0.8.106 render --help` first; use an output flag if one exists, else the newest file in `workdir/renders/`). Then `ffmpeg -y -i in -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart out`. Honour env `HYPERFRAMES_BROWSER_PATH`. Pass `--experimental-fast-capture=false` (known render fix on this machine).

- [ ] **Step 1: Tests:** `test_roast_text_verbatim_in_html` (a headline with `'` and `&` appears escaped and exact), `test_missing_broll_uses_dark_bg`, `test_total_duration_matches_recipe`, `test_text_blocks_inside_safe_box` (parse inline `top/left` of `.txt` elements ≤ SAFE_BOX bounds), `test_every_block_type_renders` (a synthetic recipe containing all 7 blocks yields non-empty html/js).
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Real render check (local, slow, marked `@pytest.mark.slow`):** `pytest -m slow tests/test_renderer.py::test_real_render_each_seed` renders each seed recipe with fixed copy. Expected: 3 MP4s; `ffprobe` shows `h264`, `yuv420p`, `1080x1920`. Pratap or the executor watches one of them and confirms layout.
- [ ] **Step 6: Commit** `feat: recipe renderer on hyperframes`.

---

### Task 10: Instagram and Facebook Reels publishers

**Files:** Create `engine/publishers/{__init__,meta_http,instagram,facebook}.py`; Test `tests/test_publishers_meta.py`

**Interfaces:**
- Produces: `publish(video: Path, caption: str, app: dict, *, http=requests, sleep=time.sleep) -> Published` in both modules. `engine.publishers.get(name)` follows the slot pattern. `meta_http.call(method, url, *, creates_post: bool, **kw)`: on any exception it raises `PublishError(type name, retryable=(not creates_post) or isinstance(e, requests.ConnectTimeout) or status==429)`. Never include the URL or params in the message. Graph base `https://graph.facebook.com/v21.0`; the token goes in the `Authorization: OAuth <token>` header.
  - Instagram (resumable Reels): `POST /{ig_user_id}/media` with `media_type=REELS, upload_type=resumable, caption` → `id`. `POST https://rupload.facebook.com/ig-api-upload/v21.0/{id}` with headers `offset: 0`, `file_size`, and the body as file bytes. Poll `GET /{id}?fields=status_code` every 5 s, up to 60 tries, until `FINISHED` (`ERROR` → PublishError non-retryable). `POST /{ig_user_id}/media_publish creation_id=id` (**creates_post=True**). `GET /{media_id}?fields=permalink` for the url; a failure here is only a warning.
  - Facebook: `POST /{page_id}/video_reels upload_phase=start` → `video_id`, `upload_url`. POST the bytes to `upload_url` with `offset: 0`, `file_size`. `POST /{page_id}/video_reels upload_phase=finish, video_id, video_state=PUBLISHED, description=caption` (**creates_post=True**). url = `https://www.facebook.com/reel/{video_id}`.
  - Secrets come from `app["meta"]` names via `secret()`.

- [ ] **Step 1: Tests (the fake http records calls and returns scripted responses):** `test_ig_full_flow_order`, `test_ig_container_error_raises_nonretryable`, `test_ig_publish_timeout_is_not_retryable` (ReadTimeout on media_publish → retryable False), `test_fb_full_flow`, `test_token_never_in_url_or_error`.
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: instagram and facebook reels publishers`.

---

### Task 11: Orchestrator (`engine run`)

**Files:** Create `engine/main.py`; Test `tests/test_main.py`

**Interfaces:**
- Consumes everything above.
- Produces: `run(root: Path, now: datetime, *, deps: Deps) -> list[dict]` (returns the events written). `Deps` is a dataclass of injectable callables: `llm, broll, music, render, publishers: dict[str, fn], rng`. The CLI `python -m engine.main run` builds the real Deps from `config.yaml`.
- Algorithm per app (stop all apps if `PAUSE` exists at root):
  1. `events = read(ledger)`. Any `publishing` event older than 30 min with no later status for the same (slot, platform) → append `unknown` (never re-post).
  2. `due_slots(...)`. Drop platforms that are auto-paused: the last 2 final events for (app, platform) are both `failed`/`unknown`, with none after `platforms.<p>.resume_after` (ISO, optional) counted.
  3. Per due slot: `plan_slot` → append `planned` → `write_copy` (on `CopyRejected` append `dropped` with the reason and continue) → b-roll (query = a random entry from `copy/keywords.yaml`) → music → `render` (exception → `dropped`, continue).
  4. Per platform: if `DRY_RUN != "0"` → append `dry_run` with the mp4 path. Otherwise append `publishing` → `publish` → append `published` (post_id, url) or `failed` (error type, retryable). Never retry in the same run.
- [ ] **Step 1: Tests (tmp root, fake deps, fixed `now`):**
```python
def test_dry_run_default_never_calls_publish(): ...
def test_publishing_logged_before_publish_call(): fake publish asserts the ledger already has "publishing"
def test_second_run_same_slot_does_not_publish(): run twice same now → publish called once per platform
def test_stale_publishing_becomes_unknown_not_retried(): ...
def test_copy_rejected_drops_slot_continues(): 2 due slots, first rejected → second still published
def test_render_failure_drops_slot(): ...
def test_two_failures_auto_pause_platform(): ...
def test_resume_after_clears_pause(): ...
def test_pause_file_stops_everything(): ...
```
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS** (full suite `pytest -q`, excluding slow).
- [ ] **Step 5: Local end-to-end dry run:** `DRY_RUN=1 python -m engine.main run --now 2026-12-05T08:05-05:00`. Expected: 1 `dry_run` line per enabled platform in `state/scrollsmack/ledger.jsonl` and a playable MP4 in `out/`.
- [ ] **Step 6: Commit** `feat: run orchestrator with ledger safety rules`.

---

### Task 12: Daily Telegram report

**Files:** Create `engine/report.py`; modify `engine/main.py` (add `report` subcommand); Test `tests/test_report.py`

**Interfaces:**
- Produces: `build_report(events: list[dict], day: date, apps: list[str]) -> str` (per app: published count per platform with urls, dropped with reasons, failed, unknown flagged "check manually", auto-paused platforms; plain text ≤ 4096 chars). `send(text, *, http=requests)` → `POST https://api.telegram.org/bot<token>/sendMessage` with `chat_id` from `TELEGRAM_CHAT_ID`. Errors re-raised as the type name only (the token is in the URL path).
- [ ] **Step 1: Tests:** `test_report_counts_and_flags_unknown`, `test_report_truncates_to_4096`, `test_send_error_hides_token`.
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat: daily telegram report`.

---

### Task 13: Workflows, docs and setup checklist

**Files:** Create `.github/workflows/run.yml`, `.github/workflows/report.yml`, `README.md`, `CLAUDE.md`, `docs/setup.md`

- `run.yml`: `on: schedule: - cron: "*/30 * * * *"` + `workflow_dispatch` (inputs: `dry_run`, default `"1"`). `concurrency: {group: engine-run, cancel-in-progress: false}`. `permissions: contents: write`. Steps: checkout, setup-python 3.12, setup-node 22, `pip install .`, `sudo apt-get install -y ffmpeg` (if missing), `python -m engine.main run` with env `ENGINE_SECRETS: ${{ toJSON(secrets) }}`, `DRY_RUN: ${{ inputs.dry_run || vars.DRY_RUN || '1' }}`, `HYPERFRAMES_BROWSER_PATH: /usr/bin/google-chrome`. Then, if the ledger changed: `git pull --rebase` and commit `state/` as `engine-bot`, then push. Upload `out/*.mp4` as an artifact (7-day retention). Every `uses:` pinned to a full SHA with the version in a comment.
- `report.yml`: cron `"30 4 * * *"` (23:30 ET in winter, 00:30 in summer) + dispatch, `permissions: contents: read`, runs `python -m engine.main report`.
- `README.md`: what it is; the slot contracts (one line each, copied from the Interfaces above); how to add an app, a recipe and a provider; `PAUSE`; `DRY_RUN`.
- `CLAUDE.md`: the non-obvious rules from Global Constraints plus the two Review Focus safety rules. Also: GitHub disables scheduled workflows in public repos after 60 days without repository activity. The bot's ledger commits keep it active, but if posting is paused for weeks, the report e-mail from GitHub ("workflow disabled") means re-enable it under the Actions tab.
- `docs/setup.md`, Pratap's checklist:
  1. Create the FB Page; switch IG to Professional; link them.
  2. Create a Meta app (Business type) and add Pratap as admin. Products: Instagram Graph API + Facebook Login. Generate a long-lived Page token with `instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement, pages_manage_posts, publish_video`. Note the IG user id and Page id.
  3. Get a Pexels API key.
  4. Create the public GitHub repo `marketing-engine`; push; enable secret scanning push protection.
  5. Add secrets: `GEMINI_API_KEY, PEXELS_API_KEY, SCROLLSMACK_META_PAGE_TOKEN, SCROLLSMACK_IG_USER_ID, SCROLLSMACK_FB_PAGE_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID`.
  6. Run `run.yml` manually with dry_run=1 for 2 days; watch the artifacts.
  7. After Dec 4: set repo variable `DRY_RUN=0`.

- [ ] **Step 1: Validate workflow syntax:** `npx --yes @action-validator/cli .github/workflows/run.yml` (or `actionlint` if installed). Expected: no errors. Check `grep -n "pull_request_target" .github -r` → no matches. Check `grep -nE "uses: .+@v[0-9]" .github -r` → no matches (all SHA-pinned).
- [ ] **Step 2: Full test suite** `pytest -q` → all pass.
- [ ] **Step 3: Commit** `docs: workflows, readme, setup checklist`.
- [ ] **Step 4 (moved after Task 14): Live verification (after Pratap finishes setup steps 1–5):** dispatch `run.yml` with dry_run=1 at a due time. Expected: green run, ledger commit by `engine-bot`, MP4 artifact. Then a single `dry_run=0` dispatch with a test `post_times` entry. Expected: one Reel live on IG and FB, and `published` lines with urls.

---

### Task 14: Onboarding a new app (`check-app` + `/add-app` skill)

**Files:** Modify `engine/main.py` (add the `check-app` subcommand); Create `engine/checkapp.py`, `.claude/skills/add-app/SKILL.md`, `docs/add-an-app.md`; Test `tests/test_checkapp.py`, `tests/fixtures/apps/newapp/` (a minimal app: `app.yaml`, `facts.yaml`, `copy/{style.md,hashtags.yaml,keywords.yaml}`)

**Interfaces:**
- Consumes: `load_app`, `load_recipes`, `validate_recipe`, `write_copy`, `render`, Deps (Tasks 1–11).
- Produces:
  - `check_app(root: Path, name: str) -> list[str]` (empty = ready). Checks: `app.yaml` has the required keys (`name, store_url, timezone, post_times, platforms, brand.colors, brand.icon`, plus a `meta` secret-name block if any Meta platform is enabled); the icon file exists; `facts.yaml` has ≥ 5 facts; `hashtags.yaml` has ≥ 5 tags; `keywords.yaml` has ≥ 3; `style.md` is non-empty; at least one recipe loads for the app; every clip in `clips.yaml` exists and is < 100 MB; no platform is enabled while `enabled_on` is missing.
  - CLI `python -m engine.main check-app <name> [--preview N]`: prints the problems (exit 1 if any). With `--preview N` (default 0) it plans, writes and renders N videos with **DRY_RUN forced on** into `out/preview/<name>/` and writes nothing to the ledger.
- `.claude/skills/add-app/SKILL.md` (a Claude Code skill; Pratap types `/add-app <repo path or store URL>` inside `marketing-engine`). Steps it instructs:
  1. Read the source: the app repo's `CLAUDE.md`/README, store listing copy, `strings.xml` or equivalent, the website, screenshots. For a URL, fetch the store page.
  2. Draft `apps/<slug>/` from `tests/fixtures/apps/newapp/` as the template: facts only from what the sources state (cite the source file per fact in a YAML comment), style, hashtags, niche keywords, brand colors/fonts/icon, timezone and post_times copied from ScrollSmack, every platform `enabled: false`.
  3. Copy any existing promo clips/screen recordings into `footage/` with `clips.yaml`.
  4. Run `python -m engine.main check-app <slug> --preview 3` and fix problems until it is clean.
  5. Show Pratap `facts.yaml` and the 3 preview MP4s, and ask him to approve the facts. **This is the one human review per app**, because facts bound every AI claim.
  6. After approval: list the account secrets to create (names from `app.yaml: meta`). Set `enabled: true` and `enabled_on: <tomorrow>`, then commit.
- `docs/add-an-app.md`: the same flow for a human, plus how to share an existing account (point `meta` at another app's secret names).

- [ ] **Step 1: Tests:** `test_fixture_newapp_passes`, `test_missing_facts_reported`, `test_enabled_without_enabled_on_reported`, `test_missing_icon_reported`, `test_preview_never_touches_ledger` (fake deps; the ledger file is unchanged after `--preview 2`).
- [ ] **Step 2: Run → FAIL. Step 3: Implement `checkapp.py`, the CLI, the skill and the doc. Step 4: Run → PASS.**
- [ ] **Step 5: Verify the skill end to end on ScrollSmack itself:** `python -m engine.main check-app scrollsmack --preview 2` → no problems, 2 MP4s in `out/preview/scrollsmack/`.
- [ ] **Step 6: Commit** `feat: check-app command and /add-app onboarding skill`.
