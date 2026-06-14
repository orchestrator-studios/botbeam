---
name: botbeam
description: Beam rich content to the user's BotBeam displays, or stash it in a lockbox for later — push a dashboard, table, markdown, html, url, image, or list to a display tab the user watches in a browser, or save a payload off-screen that the user (or another of their agents, in another context) can retrieve later. Use when the user asks to "beam" something, "put that on my display / screen / BotBeam," or to "stash" / "save" / "cache" something for later.
allowed-tools: Bash(python *)
---

# botbeam

The **companion-UX capability** — orchestra's auxiliary surface, the displays the agent beams views onto (see [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md) §3 and [`docs/design/auxiliary-plane.md`](../../../../docs/design/auxiliary-plane.md)). The user runs a BotBeam page in the browser; this skill pushes **entries ("devices")** to it over an authenticated REST API. The service is [`orchestrator-studios/botbeam`](https://github.com/orchestrator-studios/botbeam). **Hard boundary** — BotBeam enforces its own rules; the skill just calls it.

## The model

One **user-scoped key-value store**. Each entry ("device") is one of two **kinds**:

- **`display`** — rendered live as a **tab** the user watches in the browser. Every user has one **default display** ("Main") that always exists; bare `beam` targets it (no id needed).
- **`lockbox`** — **stashed off-screen**: it appears in the user's lockbox panel, not the tab strip, and is retrieved on demand. Use for "save/cache this for later" and cross-context handoffs (stash in one session, read in another — same account).

Names are unique per user — resolve a user-spoken name to an `id` with `list`. Every entry can carry an optional **`description`**: a one-line summary, especially important for lockboxes (which aren't rendered, so the listing is all the user sees).

## When to reach for it — presentation mode

BotBeam is a **second channel** running alongside the conversation. The dialogue scrolls past; a beamed view **stays put** — a fixed place to set the thing you're discussing, the way you'd pin up a handout, put a slide on the projector, or write on the whiteboard while you keep talking. The chat is the talking; the display is what's *on the wall*.

Reach for it whenever the **result deserves to be looked at, not read past**:

- The user asks you to analyze / compare / summarize something and wants the output **as an artifact** — a clean, rendered thing — not buried in the terminal or scrolling away in the chat.
- A figure you'll **keep pointing back to** ("as you can see on your screen…") while the conversation moves on around it.
- A **living view you update in place** as work progresses — a dashboard that refreshes, a checklist you tick off, a status board.
- Anything that's better *shown* than *said*: KPI cards, a table of records, a rendered page, a formatted brief.

Rule of thumb: **if you'd want it up on a screen in the room rather than spoken aloud, beam it** — then refer to it in the dialogue ("I've put the breakdown on your Main display").

A few shapes this takes:
- *"Summarize these five reports."* → beam a `markdown` brief (or a `dashboard` of the key numbers) and talk the user through it, instead of dumping it inline.
- *"Track the migration as it runs."* → beam a `dashboard`/`list` and `existing --device <id>` to refresh it in place as each step completes.
- *"Keep this comparison handy for the call."* → `stash` it to a lockbox so it's there later without cluttering the screen now.

## Access

- one bundled script over the REST API: `python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py <command> [flags]` (stdlib only). Commands: `list`, `beam`, `new`, `existing`, `stash`, `clear`, `rename`, `archive`, `unarchive`, `delete`, `reset`.
- **Where the data lives:** your BotBeam account, reached at the **`botbeam`** resource's base URL in `${CLAUDE_PLUGIN_ROOT}/resources.md`. The namespace is resolved from your token server-side — never in the URL.
- **Credential** — a per-user **agent token** (a JWT), minted in the BotBeam UI:
  ```text
  app:           none
  per-user-auth: sign in to BotBeam → Home → "Mint a token"
  file:          ~/.config/orchestra/botbeam.json   (overrides: $BOTBEAM_BASE_URL + $BOTBEAM_TOKEN)
  shape:         { "base_url": "https://<your-botbeam-host>", "token": "<agent token>" }
  obtain:        self-service — each operator mints their own token in the UI
  ```

## Getting started

1. **Sign in & mint a token.** Open your BotBeam host in a browser, register / sign in, then **Home → "Mint a token."** Save it to `~/.config/orchestra/botbeam.json` in the shape shown under [Access](#access).
2. **Smoke-test the script.** `python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py list` — you should get back your devices (at least the default **"Main"** display). A `401` means the token is missing or expired; re-mint it. "Cannot reach BotBeam" means the `base_url` is wrong or the host is down.
3. **Beam your first view.** `python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py beam --type markdown --body "# Hello from BotBeam"` — it should appear live on the **Main** tab in the browser, no refresh.
4. **Ask Claude to explain the skill.** In Claude Code, ask *"explain the botbeam skill"* or *"what can you do with botbeam?"* This does double duty: it **confirms Claude can actually see the skill** (if it can't describe it, the skill isn't installed/loaded), and Claude's explanation is itself a quick, tailored tour of what's possible — a good way for a new user to discover the moves.

## Content types

`beam` / `new` / `stash` take a `--type` and a string `--body`:

| type | body format |
|---|---|
| `text` | plain string |
| `markdown` | Markdown string |
| `html` | HTML string |
| `url` | a URL (rendered in an iframe) |
| `image` | an image URL |
| `list` | JSON array of strings or `{text, checked?}` |
| `dashboard` | JSON array of `{title, value, subtitle?}` — KPI cards |
| `table` | JSON `{columns:[{id,label}], rows:[{colId:value,…}]}` |
| `json` | raw JSON string — rendered pretty-printed |

## Rules / know-how

- **Beam vs. stash.** Beam when the user wants something **on screen now** (a dashboard, a table, a live view). Stash when they want it **saved for later** ("hold onto this", "cache that", "stash it") — it goes to a lockbox, not a tab, so it won't disturb what's on their display.
- **Three beams, mirroring the API — an id only when you truly need one.** `beam` (→ `beam_default`) puts content on the **Main** display; it's the common case and takes no id. `new` (→ `beam_new`) creates a fresh named entry. `existing --device <id>` (→ `beam_existing`) replaces content on a specific entry — the **only** beam that needs an id.
- **The main display.** `beam --type … --body …` updates the user's default display in place — the simplest "put this on my screen."
- **Reuse, don't pile up.** `list` first. To update an existing entry, resolve its id and `existing --device <id>`. Keep names short and stable ("OKRs", "Pipeline").
- **Describe what you stash.** Always give a lockbox a clear `--description` (e.g. "Search results for X, cached today") — the user picks lockboxes from a list of names + descriptions.
- **Pick the right content type.** KPI cards → `dashboard`; rows/records → `table`; prose/notes → `markdown`; a live external page → `url`; a checklist → `list`.
- **Derive, don't dump.** A beamed view is usually built *from* a substrate — compose it, then beam the result.
- **Hygiene.** `clear` blanks an entry (keeps it); `archive` takes it off the display but keeps it (restorable); `delete` removes it; `reset` wipes **everything** (the default display survives, cleared) — confirm with the user first.

## Operations

```bash
# see what's there (id, name, kind, content); filter / go cheap
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py list
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py list --kind lockbox --summary

# put a dashboard on the main display
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py beam --type dashboard \
  --body '[{"title":"KRs at risk","value":"3","subtitle":"this quarter"}]'

# create a new named tab with a table
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py new --name "Pipeline" --type table \
  --body '{"columns":[{"id":"deal","label":"Deal"}],"rows":[{"deal":"Acme"}]}'

# update an existing entry in place by id (live-refreshes the browser)
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py existing --device <id> --type markdown --body '# Updated'

# stash search results in a lockbox for later
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py stash --name "ACME research" \
  --description "Search results on ACME, cached for the call" \
  --type markdown --body '# ACME\n- founded 2009\n- ...'

# rename · clear · archive · unarchive · delete · reset
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py rename --device <id> --name "Q3 OKRs"
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py clear --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py archive --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py unarchive --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py delete --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py reset
```

## FAQ

- **Where does what I beam show up?** `beam` → the user's **Main** display (updated in place). `new --name …` → a new named **tab**. `existing --device <id>` → that specific entry. `stash` → a **lockbox** in the side panel, not a tab. All live-refresh the browser over WebSocket.
- **Beam or stash?** Beam = on screen now. Stash = saved for later / handed off to another session (same account) without touching what's on screen. Same store either way — it's purely presentation.
- **Will I clobber what's already up?** `existing --device <id>` replaces *that* entry's content only. `clear` blanks an entry but keeps it; `archive` takes it off the strip (restorable); `delete` removes one; **`reset` wipes everything** (Main survives, cleared) — so confirm before reset.
- **Can someone else see a display?** Yes — from the BotBeam UI the owner can **share a display (view-only)** with another BotBeam account by email; it shows up under that user's **"Shared with me"** and tracks the owner's beams live. Sharing is a UI action; the skill itself only reads/writes the owner's own devices.
- **Can I dedicate a screen to one display?** Yes — **pin** it (the 📌 on a tab, or open `…/?pin=<name>`). That browser then shows only that display, kiosk-style, and won't follow beams to other tabs — handy for a wall screen, a meeting room, or a kitchen display. Unpin from the bar.
- **Something's off — 401 / can't reach BotBeam / nothing updates.** `401` → re-mint the token. "Cannot reach" → check `base_url` / host. No live update though content changed → the browser may be pointed at a *different* host than the skill is beaming to (they can share a DB but not live updates) — confirm both use the same base URL.

## Notes

- The user watches displays in the browser at the `botbeam` resource's base URL (signed in); content pushes appear live (WebSocket). Lockboxes show up in a side panel; opening one renders its stashed content.
- Beam vs. stash is purely presentation — same store, same owner. Lockboxes make BotBeam a stash-and-retrieve scratchpad across the user's sessions and agents.
