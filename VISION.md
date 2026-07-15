# BotBeam — the vision

*The boiled-down statement. `README.md` and `CLAUDE.md` describe what is built;
this describes what BotBeam is; `SPEC.md` pins it down into schemas and
contracts, use-case-first. Drafted 2026-07-12; revised 2026-07-15 to match the
spec (chatmail's intelligence placed off-board, the two-part payload, the
three-gap build map).*

**BotBeam is the exchange where agents and humans trade payloads.** An agent can
send a payload to it; an agent can retrieve a payload from it; so can a person.
Because it is the one place every agent talks to, it is also — for free — the
entry point for monitoring and managing the fleet. And a payload is not just
data: payloads climb a ladder from inert content to rendered displays to
interactive surfaces to full behaviors.

That's the whole idea. Four claims, each load-bearing:

## 1. It is an exchange

The primitive operations are **send** and **retrieve**. Store-and-forward,
addressed, durable: a payload posted now can be picked up later, by whoever it
was addressed to. The endpoints are symmetric — agent→human (a report beamed to
a tab), human→agent (a thought dropped in an inbox, an approval tapped on a
phone), and agent→agent (one workspace's output is another's input). Today's
write-only "beam to a display tab" is one arrow of this; the exchange is all of
them.

## 2. It is one place

Every agent in the estate talks to BotBeam. Centrality is the feature:

- **Monitoring falls out.** Watching the exchange *is* watching the fleet —
  what each agent last sent, when, to whom. No agent needs instrumenting; its
  traffic is its telemetry.
- **Management falls out.** The same channel that carries payloads *out*
  carries commands *in*. A tab with buttons is a remote control; a queued
  payload addressed to an agent is a standing instruction it drains on its next
  session. BotBeam is where you stand to see everything and where you stand to
  steer everything.

## 3. Payloads have a liveness ladder

Every payload sits on one rung; the rungs are cumulative:

| Rung | The payload is… | Example |
|---|---|---|
| **Data** | inert content, machine- or human-readable | a JSON blob, a markdown file |
| **Display** | rendered, typed, watchable | the life-tracker board on its tab |
| **Interface** | interactive — it emits events back into the exchange | an approval card, a form, a row-picker |
| **Behavior** | a conversation — it ships knowledge an agent answers from | **chatmail**: a summary whose deep part is a corpus the reader's agent chats over |

One structural idea underlies the upper rungs: **every payload is two-part** —
a *surface* it shows and a *deep part* it ships. The deep part is retrievable,
never rendered: a report travels with its underlying data; an approval card
carries the full context so the user can ask their agent *"why am I being asked
this?"* before tapping; chatmail's deep part is its corpus. Deep is not secret —
it is content the sender chose to ship, readable by any recipient's agent. It is
unrendered, not protected.

**Chatmail** is the exemplar of the top rung and worth naming precisely: a
payload that arrives like mail — a summary you can read in ten seconds — but can
be interrogated: type a question under it and the answer lands in the thread.
Its structure is the two-part payload: the surface is the summary, the deep part
is the corpus behind it, shipped onboard. Its intelligence is **not onboard**:
the question routes to the *reader's own agent*, which reads the deep part and
answers. That placement is what makes it genuinely mail — self-contained
(forward it, and the recipient's agent answers from the same onboard corpus; the
sender's machine can be off forever) and asynchronous (replies arrive when an
agent next drains its inbox, which is how mail has always behaved — a
remote-control wakeup just makes it fast mail). BotBeam stores, renders, and
routes; it never runs a model.

## 4. Consumers are symmetric

Any payload can be retrieved by a human *or* an agent. The same beamed report
is glanced at on a phone and pulled by a downstream agent as input. This is
what makes BotBeam infrastructure rather than a UI: the human-facing surface
and the agent-facing API are two faces of one exchange, and nothing is
"rendered only."

## The discipline that keeps it honest

BotBeam holds payloads; it never becomes the system of record. A workspace's
truth lives in its own substrate behind its own tools; what BotBeam receives
are **views** (rendered from that truth) and what it hands back are **events
and intents** (applied to that truth only through the workspace's own tools).
The moment a tab becomes an editable document, BotBeam is a second source of
truth and the model breaks. Displays render; interactions emit; the owner
applies.

## Where today's build sits on this map

- **Have:** rungs 1–2 shipped — nine content types on display tabs, live over
  WS; lockbox stash-and-retrieve (one slot); view-only shares, live to
  grantees; a Memory subsystem (durable recall by key); one JWT for browser
  and agent alike.
- **Missing** — pinned down in `SPEC.md` as three structural gaps, in
  dependency order:
  1. **Payload as a row** — append-only, ordered, attributable, ackable. Today
     content is a mutable column and every beam destroys the last payload.
     Everything else stands on this.
  2. **Agent identity** — today the agent authenticates *as the user*; no
     attribution, no addressing, no fleet. One table + per-agent tokens, and
     monitoring falls out of the data.
  3. **The return channel** — inbox channels, reply threading, interaction
     payloads (approvals, forms, selections), drain-on-entry.

  Then chatmail is assembly, not construction: the surface/deep split, thread
  rendering, and the routing rule — nothing in BotBeam runs a model.
