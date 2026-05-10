"""Strava OAuth + activity sync. Token cache in coach/.strava_tokens.json (gitignored)."""
from __future__ import annotations
import json, os, time, webbrowser, urllib.parse, http.server, threading, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

from . import db

ROOT = Path(__file__).parent
TOKEN_FILE = ROOT / ".strava_tokens.json"
ENV_FILE = ROOT / ".env"

API_BASE = "https://www.strava.com/api/v3"
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPE = "read,activity:read_all"
DEFAULT_REDIRECT = "http://localhost:8731/callback"


def _load_env() -> dict[str, str]:
    """Read CLIENT_ID / CLIENT_SECRET from coach/.env."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _load_tokens() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def _save_tokens(t: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(t, indent=2))
    os.chmod(TOKEN_FILE, 0o600)


def _refresh_if_needed(tokens: dict, env: dict) -> dict:
    if tokens.get("expires_at", 0) > time.time() + 60:
        return tokens
    r = requests.post(TOKEN_URL, data={
        "client_id": env["STRAVA_CLIENT_ID"],
        "client_secret": env["STRAVA_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }, timeout=30)
    r.raise_for_status()
    new = r.json()
    tokens.update({
        "access_token": new["access_token"],
        "refresh_token": new["refresh_token"],
        "expires_at": new["expires_at"],
    })
    _save_tokens(tokens)
    return tokens


def first_time_auth() -> dict:
    """Run once. Opens browser; captures redirect via local HTTP server."""
    env = _load_env()
    if "STRAVA_CLIENT_ID" not in env or "STRAVA_CLIENT_SECRET" not in env:
        print("Missing STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET.", file=sys.stderr)
        print(f"Create {ENV_FILE} with:", file=sys.stderr)
        print("  STRAVA_CLIENT_ID=12345", file=sys.stderr)
        print("  STRAVA_CLIENT_SECRET=abcd...", file=sys.stderr)
        sys.exit(1)

    redirect_uri = DEFAULT_REDIRECT
    auth_url = f"{AUTH_URL}?" + urllib.parse.urlencode({
        "client_id": env["STRAVA_CLIENT_ID"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "approval_prompt": "auto",
        "scope": SCOPE,
    })

    received: dict[str, Any] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/callback"):
                qs = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(qs)
                if "code" in params:
                    received["code"] = params["code"][0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>OK</h1><p>You can close this tab.</p>")
                else:
                    self.send_response(400); self.end_headers()
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *_a, **_kw): pass

    server = http.server.HTTPServer(("localhost", 8731), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Opening browser → {auth_url}")
    webbrowser.open(auth_url)
    print("Waiting for redirect on http://localhost:8731/callback ...")
    while "code" not in received:
        time.sleep(0.5)
    server.shutdown()

    r = requests.post(TOKEN_URL, data={
        "client_id": env["STRAVA_CLIENT_ID"],
        "client_secret": env["STRAVA_CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": received["code"],
    }, timeout=30)
    r.raise_for_status()
    t = r.json()
    tokens = {
        "access_token": t["access_token"],
        "refresh_token": t["refresh_token"],
        "expires_at": t["expires_at"],
        "athlete_id": t.get("athlete", {}).get("id"),
    }
    _save_tokens(tokens)
    print("Tokens saved.")
    return tokens


def _api_get(path: str, tokens: dict, **params) -> Any:
    r = requests.get(f"{API_BASE}{path}",
                     headers={"Authorization": f"Bearer {tokens['access_token']}"},
                     params=params, timeout=30)
    if r.status_code == 401:
        raise RuntimeError("401 from Strava — token refresh likely needed")
    r.raise_for_status()
    return r.json()


def _activity_to_row(a: dict) -> dict:
    return {
        "id": a["id"],
        "start_dt": a["start_date"],          # ISO-8601 UTC
        "type": a.get("sport_type") or a.get("type"),
        "name": a.get("name"),
        "distance_m": a.get("distance"),
        "moving_s": a.get("moving_time"),
        "elapsed_s": a.get("elapsed_time"),
        "avg_hr": a.get("average_heartrate"),
        "max_hr": a.get("max_heartrate"),
        "avg_speed": a.get("average_speed"),
        "gap_speed": None,
        "total_ascent": a.get("total_elevation_gain"),
        "cadence": a.get("average_cadence"),
        "calories": a.get("calories"),
        "perceived_exertion": a.get("perceived_exertion"),
        "suffer_score": a.get("suffer_score"),
        "has_heartrate": 1 if a.get("has_heartrate") else 0,
        "raw_json": json.dumps(a),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def sync(since_dt: datetime | None = None, page_size: int = 50, max_pages: int = 20) -> tuple[int, int]:
    """Pull activities newer than `since_dt`. Returns (new, updated)."""
    db.init()
    env = _load_env()
    tokens = _load_tokens()
    if tokens is None:
        tokens = first_time_auth()
    tokens = _refresh_if_needed(tokens, env)

    if since_dt is None:
        last = db.get_state("last_sync_after")
        since_dt = datetime.fromisoformat(last) if last else datetime(2018, 1, 1, tzinfo=timezone.utc)

    after_epoch = int(since_dt.timestamp())
    new = updated = 0
    for page in range(1, max_pages + 1):
        batch = _api_get("/athlete/activities", tokens, after=after_epoch, per_page=page_size, page=page)
        if not batch:
            break
        for a in batch:
            row = _activity_to_row(a)
            inserted = db.upsert_activity(row)
            if inserted: new += 1
            else: updated += 1
        if len(batch) < page_size:
            break

    db.set_state("last_sync_after", datetime.now(timezone.utc).isoformat())
    return new, updated


def fetch_one(activity_id: int) -> dict:
    """Pull a single activity in detail (used after webhook or for backfill)."""
    env = _load_env()
    tokens = _refresh_if_needed(_load_tokens() or first_time_auth(), env)
    a = _api_get(f"/activities/{activity_id}", tokens)
    db.upsert_activity(_activity_to_row(a))
    return a


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--auth", action="store_true", help="One-time OAuth flow")
    p.add_argument("--since-days", type=int, default=None)
    args = p.parse_args()

    if args.auth:
        first_time_auth()
        sys.exit(0)

    since = None
    if args.since_days:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
    new, upd = sync(since)
    print(f"Synced: {new} new, {upd} updated")
