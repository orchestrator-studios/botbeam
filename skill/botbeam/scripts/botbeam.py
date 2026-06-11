#!/usr/bin/env python3
"""botbeam — beam content to your BotBeam displays over the authenticated REST API.

Creds: ~/.config/orchestra/botbeam.json  ->  {"base_url": "...", "token": "..."}
(overridable via $BOTBEAM_CREDS / $BOTBEAM_BASE_URL / $BOTBEAM_TOKEN).
Auth: sends `Authorization: Bearer <token>` (the agent token minted in the BotBeam UI).
Stdlib only — no third-party deps.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTENT_TYPES = ["text", "markdown", "html", "url", "image", "list", "dashboard", "table"]


def load_creds():
    base = os.environ.get("BOTBEAM_BASE_URL")
    token = os.environ.get("BOTBEAM_TOKEN")
    path = os.environ.get("BOTBEAM_CREDS") or os.path.expanduser("~/.config/orchestra/botbeam.json")
    if not (base and token):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            sys.exit(f"No creds at {path}. Sign in to BotBeam, mint an agent token, and save "
                     f'{{"base_url": "...", "token": "..."}} there.')
        except json.JSONDecodeError as e:
            sys.exit(f"Creds file {path} is not valid JSON: {e}")
        base = base or data.get("base_url")
        token = token or data.get("token")
    if not base or not token:
        sys.exit(f"Creds must provide base_url and token (file: {path}).")
    return base.rstrip("/"), token


def api(method, path, body=None):
    base, token = load_creds()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("401 Unauthorized — token missing or expired. Re-mint it in the BotBeam UI.")
        sys.exit(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach BotBeam at {base}: {e.reason}")


def _content(args):
    if args.type and args.body:
        return {"type": args.type, "body": args.body}
    if args.type or args.body:
        sys.exit("Provide both --type and --body together (or neither).")
    return None


def main():
    p = argparse.ArgumentParser(prog="botbeam", description="Beam content to your BotBeam displays.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List display tabs (id, name, current content).")

    b = sub.add_parser("beam", help="Create a new display tab, optionally with content.")
    b.add_argument("--name", required=True)
    b.add_argument("--type", choices=CONTENT_TYPES)
    b.add_argument("--body")

    u = sub.add_parser("update", help="Update a tab: push content and/or rename.")
    u.add_argument("--device", required=True)
    u.add_argument("--type", choices=CONTENT_TYPES)
    u.add_argument("--body")
    u.add_argument("--name")

    c = sub.add_parser("clear", help="Clear a tab's content (keep the tab).")
    c.add_argument("--device", required=True)

    d = sub.add_parser("delete", help="Delete a tab.")
    d.add_argument("--device", required=True)

    sub.add_parser("reset", help="Delete ALL tabs.")

    args = p.parse_args()

    if args.cmd == "list":
        print(json.dumps(api("GET", "/api/devices"), indent=2))
    elif args.cmd == "beam":
        body = {"name": args.name}
        content = _content(args)
        if content:
            body["content"] = content
        print(json.dumps(api("POST", "/api/devices", body), indent=2))
    elif args.cmd == "update":
        body = {}
        if args.name:
            body["name"] = args.name
        content = _content(args)
        if content:
            body["content"] = content
        if not body:
            sys.exit("Nothing to update — pass --name and/or --type with --body.")
        print(json.dumps(api("PATCH", f"/api/devices/{args.device}", body), indent=2))
    elif args.cmd == "clear":
        print(json.dumps(api("PATCH", f"/api/devices/{args.device}", {"content": None}), indent=2))
    elif args.cmd == "delete":
        api("DELETE", f"/api/devices/{args.device}")
        print(f"Deleted {args.device}")
    elif args.cmd == "reset":
        api("DELETE", "/api/devices")
        print("All tabs cleared.")


if __name__ == "__main__":
    main()
