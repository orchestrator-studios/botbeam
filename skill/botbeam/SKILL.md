---
name: botbeam
description: Beam rich content to the user's BotBeam displays, or stash it in a lockbox for later — push a dashboard, table, markdown, html, url, image, or list to a display tab the user watches in a browser, or save a payload off-screen that the user (or another of their agents, in another context) can retrieve later. Use when the user asks to "beam" something, "put that on my display / screen / BotBeam," or to "stash" / "save" / "cache" something for later.
allowed-tools: Bash(python *)
---

# botbeam

The **companion-UX capability** — orchestra's auxiliary surface, the displays the agent beams views onto (see [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md) §3 and [`docs/design/auxiliary-plane.md`](../../../../docs/design/auxiliary-plane.md)). The user runs a BotBeam page in the browser; this skill pushes **entries ("devices")** to it over an authenticated REST API. The service is [`orchestrator-studios/botbeam`](https://github.com/orchestrator-studios/botbeam). **Hard boundary** — BotBeam enforces its own rules; the skill just calls it.

## The model

One **user-scoped key-value store**. Each entry ("device") is one of two **kinds**:

- **`display`** — rendered live as a **tab** the user watches in the browser. Every user has one **default display** ("Main") that always exists; `beam` with no `--device` targets it.
- **`lockbox`** — **stashed off-screen**: it appears in the user's lockbox panel, not the tab strip, and is retrieved on demand. Use for "save/cache this for later" and cross-context handoffs (stash in one session, read in another — same account).

Names are unique per user — resolve a user-spoken name to an `id` with `list`. Every entry can carry an optional **`description`**: a one-line summary, especially important for lockboxes (which aren't rendered, so the listing is all the user sees).

## Access

- one bundled script over the REST API: `python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py <command> [flags]` (stdlib only). Commands: `list`, `beam`, `new`, `stash`, `clear`, `rename`, `archive`, `unarchive`, `delete`, `reset`.
- **Where the data lives:** your BotBeam account, reached at the **`botbeam`** resource's base URL in `${CLAUDE_PLUGIN_ROOT}/resources.md`. The namespace is resolved from your token server-side — never in the URL.
- **Credential** — a per-user **agent token** (a JWT), minted in the BotBeam UI:
  ```text
  app:           none
  per-user-auth: sign in to BotBeam → Home → "Mint a token"
  file:          ~/.config/orchestra/botbeam.json   (overrides: $BOTBEAM_BASE_URL + $BOTBEAM_TOKEN)
  shape:         { "base_url": "https://<your-botbeam-host>", "token": "<agent token>" }
  obtain:        self-service — each operator mints their own token in the UI
  ```

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
- **The main display.** `beam --type … --body …` (no `--device`) updates the user's default display in place — the simplest "put this on my screen."
- **Reuse, don't pile up.** `list` first. To update an existing entry, `beam --device <id>`. Keep names short and stable ("OKRs", "Pipeline").
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

# update an existing entry in place (live-refreshes the browser)
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py beam --device <id> --type markdown --body '# Updated'

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

## Notes

- The user watches displays in the browser at the `botbeam` resource's base URL (signed in); content pushes appear live (WebSocket). Lockboxes show up in a side panel; opening one renders its stashed content.
- Beam vs. stash is purely presentation — same store, same owner. Lockboxes make BotBeam a stash-and-retrieve scratchpad across the user's sessions and agents.
