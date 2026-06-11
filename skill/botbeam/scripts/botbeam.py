#!/usr/bin/env python3
"""botbeam — beam content to your BotBeam displays, or stash it in a lockbox,
over the authenticated REST API.

Creds: ~/.config/orchestra/botbeam.json  ->  {"base_url": "...", "token": "..."}
(overridable via $BOTBEAM_CREDS / $BOTBEAM_BASE_URL / $BOTBEAM_TOKEN).
Auth: sends `Authorization: Bearer <token>` (the agent token minted in the BotBeam UI).
Stdlib only — no third-party deps.

Model: one user-scoped key-value store of "devices". Each device is either a
'display' (rendered as a live tab the user watches) or a 'lockbox' (stashed
off-screen, retrieved on demand). Every user has one default display that always
exists; beam with no --device targets it. Names are unique per user.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTENT_TYPES = ["text", "markdown", "html", "url", "image", "list", "dashboard", "table", "json"]
KINDS = ["display", "lockbox"]


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
        detail = e.read().decode()[:300]
        if e.code == 409:
            sys.exit(f"409 Name already in use: {detail}")
        sys.exit(f"HTTP {e.code} on {method} {path}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach BotBeam at {base}: {e.reason}")


def _content(args, required):
    if args.type and args.body:
        return {"type": args.type, "body": args.body}
    if args.type or args.body:
        sys.exit("Provide both --type and --body together (or neither).")
    if required:
        sys.exit("This command needs content: pass both --type and --body.")
    return None


def _print(obj):
    print(json.dumps(obj, indent=2))


def main():
    p = argparse.ArgumentParser(
        prog="botbeam", description="Beam content to your BotBeam displays, or stash it in a lockbox.")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="List entries (id, name, kind, content).")
    ls.add_argument("--kind", choices=KINDS, help="Filter to one kind.")
    ls.add_argument("--archived", action="store_true", help="Show the archive instead of active entries.")
    ls.add_argument("--summary", action="store_true", help="Omit content bodies (cheaper for scanning).")

    bm = sub.add_parser("beam", help="Put content on the main display (or --device to update an existing entry).")
    bm.add_argument("--device", help="Target an existing entry by id (default: the main display).")
    bm.add_argument("--type", choices=CONTENT_TYPES, required=True)
    bm.add_argument("--body", required=True)

    nw = sub.add_parser("new", help="Create a new named entry, optionally with content.")
    nw.add_argument("--name")
    nw.add_argument("--description")
    nw.add_argument("--kind", choices=KINDS, default="display")
    nw.add_argument("--type", choices=CONTENT_TYPES)
    nw.add_argument("--body")

    st = sub.add_parser("stash", help="Stash content in a new lockbox (shorthand for: new --kind lockbox).")
    st.add_argument("--name")
    st.add_argument("--description", help="Short summary of what's stashed (recommended — the lockbox isn't rendered).")
    st.add_argument("--type", choices=CONTENT_TYPES, required=True)
    st.add_argument("--body", required=True)

    cl = sub.add_parser("clear", help="Clear an entry's content, keep the entry. Default: the main display.")
    cl.add_argument("--device")

    rn = sub.add_parser("rename", help="Rename an entry.")
    rn.add_argument("--device", required=True)
    rn.add_argument("--name", required=True)

    ar = sub.add_parser("archive", help="Archive an entry (off the display, restorable).")
    ar.add_argument("--device", required=True)

    un = sub.add_parser("unarchive", help="Restore an archived entry.")
    un.add_argument("--device", required=True)

    dl = sub.add_parser("delete", help="Delete an entry.")
    dl.add_argument("--device", required=True)

    sub.add_parser("reset", help="Delete ALL entries (the default display survives, cleared).")

    args = p.parse_args()

    if args.cmd == "list":
        q = []
        if args.kind:
            q.append(f"kind={args.kind}")
        if args.archived:
            q.append("archived=true")
        if args.summary:
            q.append("view=summary")
        _print(api("GET", "/api/devices" + (("?" + "&".join(q)) if q else "")))

    elif args.cmd == "beam":
        content = {"type": args.type, "body": args.body}
        path = f"/api/devices/{args.device}/content" if args.device else "/api/devices/default/content"
        _print(api("PUT", path, content))

    elif args.cmd == "new":
        body = {"name": args.name, "kind": args.kind, "description": args.description}
        content = _content(args, required=False)
        if content:
            body["content"] = content
        _print(api("POST", "/api/devices", body))

    elif args.cmd == "stash":
        body = {"name": args.name, "kind": "lockbox", "description": args.description,
                "content": {"type": args.type, "body": args.body}}
        _print(api("POST", "/api/devices", body))

    elif args.cmd == "clear":
        path = f"/api/devices/{args.device}/content" if args.device else "/api/devices/default/content"
        _print(api("DELETE", path))

    elif args.cmd == "rename":
        _print(api("PATCH", f"/api/devices/{args.device}", {"name": args.name}))

    elif args.cmd == "archive":
        _print(api("POST", f"/api/devices/{args.device}/archive"))

    elif args.cmd == "unarchive":
        _print(api("POST", f"/api/devices/{args.device}/unarchive"))

    elif args.cmd == "delete":
        api("DELETE", f"/api/devices/{args.device}")
        print(f"Deleted {args.device}")

    elif args.cmd == "reset":
        api("DELETE", "/api/devices")
        print("All entries cleared (default display kept).")


if __name__ == "__main__":
    main()
