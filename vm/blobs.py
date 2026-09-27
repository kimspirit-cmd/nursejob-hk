#!/usr/bin/env python3
"""Netlify Blobs helper: read/write the jobs store from outside Netlify.

Uses the Blobs REST API (https://api.netlify.com/api/v1/blobs/...) with a
Netlify token. From this VM the token is supplied via the dynamic credential
surrogate (custom.netlify).
"""
import json
import sys
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import (
    dynamic_credential_entry,
    ensure_allowed_url,
    read_json_response,
)

SITE_ID = "de158393-11ce-46e5-a676-6b671dafdc24"
STORE = "jobs"
API = "https://api.netlify.com"
ALLOWED = ["api.netlify.com"]
SIGNED_URL_ACCEPT = "application/json;type=signed-url"


def _token():
    entry = dynamic_credential_entry("custom.netlify", "access_token")
    return entry["surrogate"]


def _api_request(url, method, accept_signed_url=False):
    ensure_allowed_url(url, ALLOWED)
    headers = {}
    if accept_signed_url:
        headers["Accept"] = SIGNED_URL_ACCEPT
    req = urllib.request.Request(url, method=method, headers=headers)
    req.add_header("Authorization", f"Bearer {_token()}")
    return req


def _signed_url(key, method):
    url = f"{API}/api/v1/blobs/{SITE_ID}/{STORE}/{key}"
    req = _api_request(url, method, accept_signed_url=True)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = read_json_response(resp)
    return data["url"]


def get_json(key):
    """Return the parsed JSON at key, or None if missing."""
    try:
        signed = _signed_url(key, "GET")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    try:
        with urllib.request.urlopen(signed, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def set_json(key, obj):
    """Write obj as JSON to key."""
    signed = _signed_url(key, "PUT")
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        signed, data=payload, method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"Blobs PUT failed: HTTP {resp.status}")


def delete(key):
    url = f"{API}/api/v1/blobs/{SITE_ID}/{STORE}/{key}"
    req = _api_request(url, "DELETE")
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Blobs DELETE failed: HTTP {resp.status}")


if __name__ == "__main__":
    # CLI: blobs.py get <key> | set <key> <json-file> | delete <key>
    cmd = sys.argv[1]
    if cmd == "get":
        print(json.dumps(get_json(sys.argv[2]), ensure_ascii=False))
    elif cmd == "set":
        with open(sys.argv[3], encoding="utf-8") as f:
            obj = json.load(f)
        set_json(sys.argv[2], obj)
        print(f"wrote {sys.argv[2]}")
    elif cmd == "delete":
        delete(sys.argv[2])
        print(f"deleted {sys.argv[2]}")
