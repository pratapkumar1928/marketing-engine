---
name: add-app
description: Onboard a new app into the marketing engine. Use when Pratap says "/add-app", "add <app> to the marketing engine", or "start marketing <app>". Takes a local repo path or a store URL.
---

# Add an app to the marketing engine

Goal: a ready `apps/<slug>/` folder, 3 preview videos, and Pratap's one-time approval of `facts.yaml`.
Facts are the boundary for every claim the AI will ever make about this app, so they get a human review.
Everything else is your call.

## 1. Read the sources
- Local repo: its `CLAUDE.md` / README, store listing copy (often `docs/*listing*`), the main strings file
  (`strings.xml`, `en.json`, …), the privacy policy, and screenshots.
- Store URL: fetch the listing page (description, screenshots).
- Note the app's audience, what it does, and what makes it different.

## 2. Draft `apps/<slug>/` from `tests/fixtures/apps/newapp/`
Copy that folder, then fill it in:
- `facts.yaml`: 5–15 short, true statements, each **only** from what a source states. Add a YAML comment
  with the source file on each line. Never add numbers, ratings, awards or features that aren't stated.
  The first fact appears on every end card, so make it the strongest plain one (for example "Free on Google Play.").
- `copy/style.md`: voice, target viewer, what jokes are off-limits.
- `copy/hashtags.yaml`: 8–15 niche tags. `copy/keywords.yaml`: 5–8 b-roll search phrases.
- `app.yaml`: name, store_url (with no tracking), bio_link with `utm_source={platform}`, brand colors from the app's
  theme, icon in `brand/icon.png`, and the `meta` secret names `<SLUG>_IG_USER_ID`, `<SLUG>_FB_PAGE_ID`,
  `<SLUG>_META_PAGE_TOKEN`. Keep **every platform `enabled: false`**.
- Optional: existing promo clips or screen recordings in `footage/` plus `footage/clips.yaml`
  (`id, file, dur, desc`, under 100 MB each). An app-specific visual is `blocks/app_overlay.html`; copy
  ScrollSmack's as the pattern and keep it inside x 80–950.

## 3. Check and preview
```
.venv/Scripts/python -m engine.main check-app <slug> --preview 3
```
Fix every problem it prints and run it again until it says `ready`. Previews land in `out/preview/<slug>/`.
Watch them by pulling frames: `ffmpeg -i out/preview/<slug>/preview_0.mp4 -vf "fps=1,scale=270:480,tile=9x1" -frames:v 1 sheet.png`.

## 4. Ask Pratap (the one human step)
Show `facts.yaml` and the 3 previews (publish them as an Artifact or send the files). Ask him to approve or
correct the facts. Don't enable anything before he approves.

## 5. Go live
- List the secrets to add in GitHub (from `app.yaml: meta`), plus account setup if the app gets its own
  Instagram/Facebook (see `docs/setup.md` §1–2). To share an existing account, point `meta` at that app's
  secret names instead.
- Set each platform to `enabled: true` and `enabled_on: <tomorrow>`, then commit on a branch.
