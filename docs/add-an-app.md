# Adding an app

The quick way: open Claude Code in this repo and type `/add-app <repo path or store URL>`. Claude drafts the
folder, renders previews and asks you to approve the facts. By hand it's the same steps:

1. Copy `tests/fixtures/apps/newapp/` to `apps/<slug>/`.
2. Fill in:
   - `facts.yaml`: true statements only. **Every claim the AI makes must come from here**, so this is the one
     file to read carefully. The first fact is shown on every end card.
   - `copy/style.md` (voice), `copy/hashtags.yaml` (allowed tags), `copy/keywords.yaml` (b-roll searches).
   - `app.yaml`: name, store link, brand colors, `brand/icon.png`, schedule, and the secret names under `meta`.
   - Optional: `footage/` + `footage/clips.yaml` for clip remixes, `blocks/app_overlay.html` for an app-specific visual.
3. Check and preview:
   ```
   python -m engine.main check-app <slug> --preview 3
   ```
   It must print `ready`. Previews are in `out/preview/<slug>/`; nothing is logged or posted.
4. Accounts: either give the app its own Instagram/Facebook (follow `docs/setup.md` §1–2, then add the three
   `<SLUG>_…` secrets), or share an existing account by pointing `meta` at that app's secret names.
5. Go live: set each platform to `enabled: true` with `enabled_on` = tomorrow and commit. Posting ramps from
   2 a day to the `target`.

What a new app gets without writing any code: the shared formats in `recipes/` drawn in its own colors, AI
copy checked against its facts, its own schedule and ledger, and its own lines in the daily report.
