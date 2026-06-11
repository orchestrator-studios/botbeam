---
name: botbeam
description: Beam rich content to the user's BotBeam displays — push a dashboard, table, markdown, html, url, image, or list to a named display tab the user watches in a browser beside the chat. Use when the user asks to "beam" something, "put that on my display / screen / BotBeam," or when a request is better answered with a persistent live view than inline text.
allowed-tools: Bash(python *)
---

# botbeam

The **companion-UX capability** — orchestra's auxiliary surface, the displays the agent beams views onto (see [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md) §3 and [`docs/design/auxiliary-plane.md`](../../../../docs/design/auxiliary-plane.md)). The user runs a BotBeam page in the browser; this skill pushes **display tabs ("devices")** to it over an authenticated REST API. The service is [`orchestrator-studios/botbeam`](https://github.com/orchestrator-studios/botbeam). **Hard boundary** — BotBeam enforces its own rules; the skill just calls it.

## Access

- **Tool(s):** one bundled script over the REST API — `python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py <command> [flags]` (stdlib only). Commands: `list`, `beam`, `update`, `clear`, `delete`, `reset`.
- **Where the data lives:** your BotBeam account's display tabs, reached at the **`botbeam`** resource's base URL in `${CLAUDE_PLUGIN_ROOT}/resources.md`. The namespace is resolved from your token server-side — never in the URL.
- **Credential** — a per-user **agent token** (a JWT), minted in the BotBeam UI:
  ```text
  app:           none
  per-user-auth: sign in to BotBeam → Home → "Mint a token"
  file:          ~/.config/orchestra/botbeam.json   (overrides: $BOTBEAM_BASE_URL + $BOTBEAM_TOKEN)
  shape:         { "base_url": "https://<your-botbeam-host>", "token": "<agent token>" }
  obtain:        self-service — each operator mints their own token in the UI
  ```

## Content types

`beam` / `update` take a `--type` and a string `--body`:

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

## Rules / know-how

- **Beam vs. answer inline.** Beam when the user wants a **persistent, watchable view** (a dashboard, a table, a board) or says "beam"/"put it on my display." For a quick one-off answer, reply in chat — don't spawn a tab.
- **Reuse tabs; don't pile up.** `list` first. If a fitting tab exists, `update` it (it pushes live to the browser) rather than creating a duplicate. Keep **names short and stable** ("OKRs", "Pipeline", "Bugs") so the same view updates in place.
- **Pick the right content type.** KPI cards → `dashboard`; rows/records → `table`; prose/structured notes → `markdown`; a live external page → `url` (iframe); a checklist → `list`.
- **Derive, don't dump.** A beamed view is usually built *from* a substrate (e.g. a dashboard from the OKR sheet) — compose it with the source skill's data, then beam the result.
- **Hygiene.** `clear` a stale view (keeps the tab); `delete` removes a tab; `reset` wipes **all** tabs — confirm with the user first.

## Operations

```bash
# see what's on the display (ids, names, current content)
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py list

# beam a new dashboard tab
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py beam --name "OKRs" --type dashboard \
  --body '[{"title":"KRs at risk","value":"3","subtitle":"this quarter"}]'

# update an existing tab in place (live-refreshes the browser)
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py update --device <id> --type table \
  --body '{"columns":[{"id":"kr","label":"KR"},{"id":"st","label":"Status"}],"rows":[{"kr":"Land 2 pilots","st":"At risk"}]}'

# rename · clear · delete · reset
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py update --device <id> --name "Q3 OKRs"
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py clear  --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py delete --device <id>
python ${CLAUDE_SKILL_DIR}/scripts/botbeam.py reset
```

## Notes

- The user watches their displays in the browser at the `botbeam` resource's base URL (signed in); content pushes appear live (WebSocket).
- Agent-to-agent **handoffs** (dropbox devices) exist in the BotBeam service but aren't wired into this skill yet — displays are the focus.
