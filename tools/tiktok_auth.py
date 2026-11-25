"""One-time TikTok sign-in for an app. Writes state/<app>/tiktok_token.enc (encrypted); commit that file.

  python tools/tiktok_auth.py <app>               1. prints the sign-in link
  python tools/tiktok_auth.py <app> "<address>"   2. finishes with the address TikTok sent you to

Needs in .env: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_TOKEN_KEY (the same values as the GitHub secrets).
Re-run it whenever the daily report shows "tt token refresh failed". Never prints a token.
"""
import secrets
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from cryptography.fernet import Fernet

from engine.config import REPO_ROOT, load_app, secret
from engine.publishers.tiktok import TOKEN_URL, save_token, token_path


def main(slug: str, back: str | None) -> int:
    app = load_app(REPO_ROOT, slug)
    t = app["tiktok"]
    try:
        key = secret(t["token_key_secret"])
    except KeyError:
        print(f"No {t['token_key_secret']} yet. Add this line to .env AND as a GitHub Actions secret, then re-run:\n"
              f"{t['token_key_secret']}={Fernet.generate_key().decode()}")
        return 1
    client_key, redirect = secret(t["client_key_secret"]), t["redirect_uri"]
    state_file = REPO_ROOT / "cache" / f"tiktok_auth_{slug}.state"  # cache/ is gitignored
    if back is None:
        state = secrets.token_urlsafe(16)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(state, encoding="utf-8")
        print("Open this link, signed in to the app's TikTok account, and allow access:\n")
        print("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
            {"client_key": client_key, "scope": "user.info.basic,video.upload", "response_type": "code",
             "redirect_uri": redirect, "state": state}))
        print(f'\nThen run: python tools/tiktok_auth.py {slug} "<the address you landed on>"')
        return 0
    q = parse_qs(urlparse(back).query)
    if not state_file.is_file() or q.get("state", [""])[0] != state_file.read_text(encoding="utf-8") or not q.get("code"):
        print("That address has no code or is from an older link. Run step 1 again.")
        return 1
    r = requests.post(TOKEN_URL, timeout=60, data={
        "client_key": client_key, "client_secret": secret(t["client_secret_secret"]), "code": q["code"][0],
        "grant_type": "authorization_code", "redirect_uri": redirect})
    body = r.json() if r.content else {}
    if not body.get("refresh_token") or "video.upload" not in str(body.get("scope", "")):
        print(f"Token exchange failed: HTTP {r.status_code} {str(body.get('error', ''))[:60]}")
        return 1
    path = token_path(app)
    save_token(path, key, {"access_token": body["access_token"], "refresh_token": body["refresh_token"],
                           "access_expires_at": (datetime.now(timezone.utc)
                                                 + timedelta(seconds=int(body.get("expires_in", 3600)))).isoformat()})
    state_file.unlink()
    print(f"Saved {path.relative_to(REPO_ROOT)}. Commit and push it (it's encrypted).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None) if len(sys.argv) in (2, 3)
             else print(__doc__) or 2)
