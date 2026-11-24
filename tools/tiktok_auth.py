"""One-time TikTok sign-in for an app. Writes state/<app>/tiktok_token.enc (encrypted); commit that file.

Usage: python tools/tiktok_auth.py <app-slug>
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


def main(slug: str) -> int:
    app = load_app(REPO_ROOT, slug)
    t = app["tiktok"]
    try:
        key = secret(t["token_key_secret"])
    except KeyError:
        print(f"No {t['token_key_secret']} yet. Add this line to .env AND as a GitHub Actions secret, then re-run:\n"
              f"{t['token_key_secret']}={Fernet.generate_key().decode()}")
        return 1
    client_key, redirect = secret(t["client_key_secret"]), t["redirect_uri"]
    state = secrets.token_urlsafe(16)
    print("1. Open this link, signed in to the app's TikTok account, and allow access:\n")
    print("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
        {"client_key": client_key, "scope": "video.upload", "response_type": "code",
         "redirect_uri": redirect, "state": state}))
    back = input("\n2. Paste the full address you were sent to (it starts with the redirect URI): ").strip()
    q = parse_qs(urlparse(back).query)
    if q.get("state", [""])[0] != state or not q.get("code"):
        print("That address has no code or the wrong state. Start again.")
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
    print(f"Saved {path.relative_to(REPO_ROOT)}. Commit and push it now (it's encrypted).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else print(__doc__) or 2)
