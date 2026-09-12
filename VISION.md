# BotBeam — the vision

*The boiled-down statement. `README.md` and `CLAUDE.md` describe what is built;
this describes what BotBeam is; `SPEC.md` pins it down into schemas and
contracts, use-case-first. Drafted 2026-07-12; revised 2026-07-15 to match the
spec (chatmail's intelligence placed off-board, the two-part payload, the
three-gap build map) and to put the people↔agents communication layer at the
center.*

**The vision is to turn BotBeam into the communication layer between people and
their agents.**

Today, BotBeam is essentially **glass**: an agent can publish a rendered view
to a named tab, and the user can see it anywhere. The vision is that the glass
becomes **two-way, durable, addressable, and agent-aware** — without BotBeam
itself becoming intelligent. Put differently:

> BotBeam is shared infrastructure through which agents can show users what
> they know, ask users for decisions, receive new intentions, and communicate
> with other users' agents.

The central shift is from *"beam the latest thing to a screen"* to *"exchange
durable, typed messages between users and identifiable agents."* In one
sentence:

> **BotBeam is the shared, intelligence-free communication fabric through
> which living workspaces and their agents remain visible, reachable,
> accountable, and interruptible by people.**

A note on vocabulary: in the wider story, **the glass** is a *role*, not a
product — the durable surface that stands alongside conversation between a
user and their agents, with a four-part spec: **durable** (it doesn't fly by
like conversation), **visually rich** (a board, a table, a trend line — not a
text stream), **familiar** (glancing works by recognition, not reading), and
**in the user's flow** (glanceable and actionable without leaving what you're
doing). BotBeam is the piece being built to fill that role. The four
capabilities below are what filling it means.

## What the shift buys: four capabilities

### 1. Agents can project their work into the human world

A living workspace can produce a board, report, dashboard, approval request,
or summary and beam it to a persistent channel. BotBeam owns the presentation
surface; the workspace continues to own the underlying records, queries, and
operations. This is the foundational division of labor:

> **The workspace owns the meaning and the work. BotBeam owns the glass and
> delivery.**

The surface itself has ergonomics, and they matter as much as the content. It
is **decoupled from the chat surface**, and it is organized as **named,
precise spaces** the user can visually manipulate — move a rendering from one
screen to another, keep several up at once — and that both parties can point
at by name. The collaboration model is a meeting-room whiteboard: everyone
agrees on the space around them, ideas get parked visually, and what was
parked stays exactly where it was put. The renderings themselves are the
agent's job — drawn from a **library of familiar forms** (a board, a table, a
report, a trend line) or **fabricated on the spot** when the situation or the
wanted insight is novel. BotBeam's job is that either kind lands somewhere
durable, addressable, and in the user's flow.

### 2. Users can participate in unattended agent workflows

An agent can run without the user present, reach a decision boundary, and ask:
*"Send this newsletter?"* The answer stays queued until the agent retrieves
it. This changes agents from tools that require a live conversational session
into processes that operate asynchronously while still yielding control at the
appropriate moments. It is probably the most strategically important
capability: **human-in-the-loop operation without requiring human-and-agent
co-presence.**

### 3. BotBeam becomes an intent inbox

The return path is not limited to answering agent questions. A user can drop
intentions into a workspace from a phone — *"schedule the chimney quote"* —
and later the appropriate agent drains its inbox and applies those intentions
through the workspace's own tools. BotBeam is not the system of record and
does not execute the work; it is a **durable boundary between the user's life
and the workspace runtime**.

### 4. Artifacts can carry their own conversational context

A report ships a **surface** that humans read, a **deep part** that an agent
can inspect, and a thread through which the viewer can ask questions —
answered by the *recipient's own* agent from the context shipped inside the
artifact. The originating system does not need to remain online, and BotBeam
does not need to run a model. The artifact becomes something more than a
document: a **portable conversational object** — a rendered communication with
enough onboard context for an agent to work with it. This is **chatmail**,
made precise under claim 3 below.

## The architecture: four claims

Underneath the capabilities sits one mechanism: **BotBeam is the exchange
where agents and humans trade payloads.** An agent can send a payload to it;
an agent can retrieve a payload from it; so can a person. Because it is the
one place every agent talks to, it is also — for free — the entry point for
monitoring and managing the fleet. And a payload is not just data: payloads
climb a ladder from inert content to rendered displays to interactive surfaces
to full behaviors.

Four claims, each load-bearing:

### 1. It is an exchange

The primitive operations are **send** and **retrieve**. Store-and-forward,
addressed, durable: a payload posted now can be picked up later, by whoever it
was addressed to. The endpoints are symmetric — agent→human (a report beamed to
a tab), human→agent (a thought dropped in an inbox, an approval tapped on a
phone), and agent→agent (one workspace's output is another's input). Today's
write-only "beam to a display tab" is one arrow of this; the exchange is all of
them.

### 2. It is one place

Every agent in the estate talks to BotBeam. Centrality is the feature:

- **Monitoring falls out.** Watching the exchange *is* watching the fleet —
  what each agent last sent, when, to whom. No agent needs instrumenting; its
  traffic is its telemetry.
- **Management falls out.** The same channel that carries payloads *out*
  carries commands *in*. A tab with buttons is a remote control; a queued
  payload addressed to an agent is a standing instruction it drains on its next
  session. BotBeam is where you stand to see everything and where you stand to
  steer everything.

### 3. Payloads have a liveness ladder

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

### 4. Consumers are symmetric

Any payload can be retrieved by a human *or* an agent. The same beamed report
is glanced at on a phone and pulled by a downstream agent as input. This is
what makes BotBeam infrastructure rather than a UI: the human-facing surface
and the agent-facing API are two faces of one exchange, and nothing is
"rendered only."

## The deeper idea: civic infrastructure for agents

The document may look like a messaging-system specification, but the real
vision is larger: **agents need a stable civic infrastructure outside the
systems they operate.** Living workspaces contain the data, rules, tools, and
workflows. But agents also need somewhere to:

- surface state to people;
- wait for decisions;
- receive intentions;
- exchange contextual artifacts;
- identify themselves;
- demonstrate that they are alive and functioning.

BotBeam is intended to become that external infrastructure. It is therefore
not another application, chatbot, workflow engine, or agent platform. It is
closer to a combination of a **display bus**, an **agent mailbox**, an
**interaction protocol**, an **identity and presence layer**, and a
**transport for agent-readable artifacts**.

## The unifying abstraction

The most important technical realization in the spec is that everything above
is a variation of the same primitive:

> **An identifiable user or agent sends a typed, durable payload to a
> channel.**

Everything else follows from that:

- A dashboard is a payload whose newest version is rendered.
- A capture item is a payload waiting in an inbox.
- An approval response is a payload replying to another payload.
- A chatmail conversation is a thread of payloads.
- Fleet monitoring is an aggregation of payload sender identity and activity.

That is why moving content from a mutable column to an append-only `Payload`
row (gap 1 below) is not merely a database refactor. It is the architectural
pivot that turns BotBeam from a display utility into an agent communication
substrate.

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
