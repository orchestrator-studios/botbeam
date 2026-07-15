# BotBeam — the spec, derived from use cases

*Companion to `VISION.md`. First drafted 2026-07-12 assertion-first; rewritten
2026-07-15 use-case-first: five concrete uses, each walked through what it demands
of the schema and the contract, so every field below is forced by a story rather
than asserted. The gap analysis against the current build closes the file.*

---

## The five use cases

### UC1 — Beam the board *(ships today)*

The life-tracker finishes a work session. Its beam tool re-renders the board query
as markdown and beams it to the "Life Infrastructure Backlog" tab. The user
glances at it on any device; anyone the tab is shared with sees the update live.

**Demands:** named channels with a per-user default · typed content, rendered ·
newest-wins display semantics · view-only shares with live push · WS broadcast.

**Vocabulary note:** a display channel is a *projection target* in the
living-workspace sense settled on 2026-07-10 — a query result in a rendered
format. The workspace owns the query; BotBeam owns the glass. Same discipline,
two ends of one pipe.

**Today:** ✅ works end to end — with one loss: each beam *destroys* the previous
payload (content is a mutable column). The trail of what was beamed when is
exactly the monitoring feed UC5 wants, and today it evaporates.

### UC2 — The approval gate

The newsletter's scheduled run assembles issue N007 and hits a gate that belongs
to the user: *send to subscribers?* It beams an approval card and parks. The user,
on their phone an hour later, reads the card and taps **Send**. The agent — still
running, or on its next wake — retrieves the answer and proceeds. This is the use
case that unlocks unattended runs.

**Demands:** an interaction payload type (`approval`: prompt, options, expiry) ·
the tap becomes a **new payload** — which forces *correlation* (`reply_to`: which
ask is this answering?), *addressing* (whose inbox does it land in? → the sender
must be an identifiable **Agent**, not "the user's JWT"), and *queue semantics*
(the answer must wait, unconsumed, until the agent retrieves and acks it).

**Today:** ❌ nothing flows user→agent.

### UC3 — The capture inbox

Tuesday, on a phone: the user drops "get the chimney quote scheduled" into the
life-tracker's capture channel. Wednesday, two more thoughts. Thursday's session
drains the channel on entry — three payloads, in order — and logs each through the
workspace's own tools.

**Demands:** the **user as sender** (symmetry claim 1 of the vision) · payloads
that *accumulate* rather than replace · retrieve-pending + ack ·
the **drain-on-entry** convention · the discipline that what's drained is applied
through the workspace's tools, never treated as the record itself.

**Today:** 🟡 lockbox is the right idea with a one-slot body: a second capture
destroys the first. The gap is the same one UC1 exposed — payload as column,
not row.

### UC4 — Chatmail

The newsletter beams the weekly chatmail. Its **surface** — what renders on the
tab — is the ten-second summary of the week's talc/asbestos literature. Its
**deep part** — shipped inside the payload, never rendered — is the supporting
corpus: abstracts, extracted findings, citations. The user reads the surface and
types into the card: *"did anything this week cite the Olsen cohort?"* The turn
lands in **their own agent's** inbox; Claude Code, as an ordinary BotBeam client,
retrieves it, reads the chatmail's deep part, and posts the answer into the
thread. Forward the chatmail to a colleague, and *their* agent answers *their*
questions from the same onboard deep part — the sender's machine can be off
forever.

**Demands:** the **two-part payload** — `surface` (rendered) + `deep`
(retrievable, not rendered) · `cargo_url` for deep parts past the body cap ·
chat turns as `reply_to`-threaded payloads, rendered as a thread under the
surface · a routing rule: turns go to the **viewer's** agent's inbox · and
explicitly **no intelligence in BotBeam** — it stores, renders, routes.

Three consequences worth stating:

- **Chatmail is a pattern, not a platform feature.** It is a display payload +
  the surface/deep split + the UC2/UC3 return machinery. Rung 4 of the vision's
  ladder costs BotBeam nothing beyond thread rendering.
- **The surface/deep split generalizes** — that's the tell it belongs in the
  schema, not in a chatmail special case. A beamed report ships its underlying
  data onboard; an approval card carries full context in the deep part so the
  user can ask their agent *"why am I being asked this?"* before tapping.
- **Deep ≠ secret.** The deep part is content the sender chose to ship; any
  grantee's agent can read it. It is *unrendered*, not protected.

**Latency is solved by the name:** replies arrive when an agent next drains its
inbox — which is exactly how mail behaves. A remote-control wakeup just makes it
fast mail.

**Today:** ❌ blocked on the same machinery as UC2/UC3, plus surface/deep and
thread rendering.

### UC5 — The fleet glance

The user opens the BotBeam home page: life-tracker last beamed two hours ago;
the newsletter's cron checked in this morning; claude-manager has been quiet
three days; two approvals are pending, one capture channel has unread items.
One screen answers *is everything alive, and does anything need me?*

**Demands:** the **Agent** noun — per-agent identity and tokens, `sender` stamped
on every payload, `last_seen_at` stamped on every authenticated call · pending
counts per inbox. Given those, monitoring is a `GROUP BY sender` — no agent
instruments itself, exactly as the vision claims.

**Today:** ❌ the agent authenticates *as the user* (one shared JWT), so BotBeam
cannot tell the life-tracker from the newsletter, and nothing is attributable.

---

## The schema the use cases force

Five nouns. Two exist and are already right; one generalizes; two are new.
Each field cites the use case that forces it.

### Agent *(new — forced by UC2, UC5)*

```
Agent
  agent_id        pk
  user_id         fk → users (an agent acts for exactly one user)
  name            unique per user — "life-tracker", "newsletter"     (UC5: the fleet row)
  token_hash      per-agent credential, individually revocable       (UC5: identity)
  last_seen_at    stamped on every authenticated call                (UC5: liveness)
  created_at
```

### Channel *(today's Device, generalized — UC1 has it; UC2/UC3 extend it)*

Keeps everything Device already has: 8-char public handle, per-user unique names,
one undeletable default, description, archive, view-only shares.

```
Channel
  kind            display — renders its newest live payload           (UC1)
                  lockbox — holds a stashed payload for pickup        (exists)
                  inbox   — accumulates payloads until consumed       (UC2, UC3)
  consumer        for inbox: user | agent_id — who drains it          (UC2: routing)
```

### Payload *(new as a row — the pivot; every use case touches it)*

```
Payload
  id              pk
  channel_id      fk → channels
  seq             per-channel monotonic order                         (UC3: drain in order)
  sender          user | agent_id                                     (UC3 symmetry; UC5 attribution)
  type            see the type table below
  surface         what renders — LONGTEXT, 500 KB cap as today        (UC1)
  deep            shipped, retrievable, never rendered — nullable     (UC4)
  cargo_url       S3 pointer when deep outgrows the body cap          (UC4)
  reply_to        nullable fk → payloads — threads and correlation    (UC2 answers; UC4 turns)
  status          live | superseded | consumed                        (UC1 history; UC2/UC3 ack)
  created_at, consumed_at, consumed_by
```

A display channel renders its newest `live` payload; a beam supersedes rather
than destroys (UC1's trail, UC5's feed). An inbox accumulates `live` payloads
until its consumer acks them (UC2, UC3).

**Payload types:**

| Rung | Types | Forced by |
|---|---|---|
| Data | `text` `json` `list` … | shipped |
| Display | `markdown` `html` `table` `dashboard` `image` `url` | shipped (9 types) |
| Interface | `approval` `form` `select` — surface carries the spec `{prompt, options / field-schema, expires_at}`; the response is a new payload with `reply_to` | UC2 |
| Behavior | `chatmail` — surface = summary; deep = corpus; turns = threaded payloads answered by the viewer's agent | UC4 |

### Grant *(exists — DeviceShare, unchanged; UC1 uses it, UC4 leans on it)*

### Memory *(exists — unchanged)*

A durable rung-1 payload addressed to the future, with recall-by-summary
semantics. Vision-shaped as built; not forced into the Payload table.

---

## The contracts

### HTTP

```
Send        POST /api/channels/{id}/payloads    {type, surface, deep?, reply_to?}
                                                Idempotency-Key header (agent retries)   UC2/UC3
Retrieve    GET  /api/channels/{id}/payloads    ?status=live&since_seq=N                 UC3 drain
Deep read   GET  /api/payloads/{id}/deep        the unrendered part, on demand           UC4
Ack         POST /api/payloads/{id}/ack         → consumed; idempotent (at-least-once)   UC2/UC3
Reply       POST /api/payloads/{id}/reply       sugar: send with reply_to, routed to
                                                the right inbox by the type's rule       UC2 tap, UC4 turn
Fleet       GET  /api/agents                    [{name, last_seen_at, last_sent,
                                                  inbox_pending}]                        UC5
Mint        POST /auth/agent-token {name}       one token per agent, revocable           UC5
Channels    existing device CRUD carries over: create/list/get/rename/
            archive/unarchive/delete/reset/shares                                        UC1
```

**Routing rule for replies:** an `approval`/`form`/`select` response routes to the
*sender's* inbox (the asker is waiting); a `chatmail` turn routes to the
*viewer's* agent's inbox (the knowledge is onboard, so the nearest intelligence
answers). The rule lives with the payload type, not the client.

**Today's three beams survive as sugar** — the skill keeps working unmodified:
`beam` = send to default display · `existing` = send to a channel · `stash` =
create lockbox + send. Same UX; the trail is kept.

### WebSocket

`payload_created` · `payload_acked` · channel lifecycle (today's `device_*` set,
renamed). Broadcast to owner + grantees as now (UC1); a `payload_created` on a
thread is what makes a chat answer appear live (UC4). Phone push is a later
transport for the same events (UC2's away-from-desk tap), not a new contract.

### Conventions (client-side; BotBeam does not enforce)

- **Drain on entry** — an agent's first act in a session: retrieve + ack its
  inbox (UC3), including pending answers to its own asks (UC2).
- **Views out, intents in** — BotBeam is never the system of record. What a
  workspace sends is a rendered view; what it drains is applied through its own
  tools. The record stays behind `repo.py`.
- **Deep ≠ secret** — ship nothing in a deep part you wouldn't show a grantee.

---

## Gap analysis: the schema above vs the current build

| Use case | Current build | Verdict |
|---|---|---|
| UC1 beam the board | 3 beams, 9 types, shares, WS, default display | ✅ ships — but beams destroy history |
| UC3 capture inbox | lockbox: right idea, one slot | 🟡 needs payload-as-row + ack |
| UC2 approval gate | nothing flows user→agent | ❌ needs gaps 1–3 |
| UC4 chatmail | nothing | ❌ needs gaps 1–3 + surface/deep + threads |
| UC5 fleet glance | agent *is* the user; no attribution | ❌ needs gap 2 |

**Three structural gaps, in dependency order** (unchanged from the first draft;
the use cases confirm the order rather than revise it):

1. **Payload as a row** — append-only, ordered, attributable, ackable
   (UC1's trail, UC3's queue, everything else's foundation). Migration is
   mechanical: `devices` → `channels`; each device's content columns become its
   first Payload row; beam endpoints stay as sugar, so skill and frontend keep
   working through the rename.
2. **Agent identity** — the Agent table + per-agent tokens + `sender` stamping
   (UC5 entire; UC2's addressing). Fleet monitoring then falls out of the data.
3. **The return channel** — `inbox` kind + `reply_to` + the three interaction
   types + drain-on-entry (UC2 entire; UC3's semantics).

Then **UC4 is assembly, not construction**: surface/deep on the Payload row
(part of gap 1 if done then), the deep-read endpoint, thread rendering in the
frontend, and the viewer-routing rule. The chatmail hosting question from the
first draft is resolved: the intelligence is the viewer's Claude Code, off-board;
BotBeam never runs a model.
