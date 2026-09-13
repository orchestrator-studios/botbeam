// Domain objects — mirrors backend/schemas.py: same objects, same order; keep them in sync.
// Frontend-only types (content body shapes, WS events) follow in their own sections.

// ── User ──
export interface User {
  user_id: number;
  org_id: number | null;
  role: string;
  email: string;
  username: string;
}

// ── Devices ──
export type DeviceKind = 'display' | 'lockbox';

export type ContentType = 'text' | 'markdown' | 'html' | 'url' | 'image' | 'list' | 'dashboard' | 'table' | 'json';

export interface DeviceContent {
  type: ContentType;
  body: string;
  updatedAt: string;
}

export interface Device {
  id: string;
  name: string;
  description?: string | null;
  kind?: DeviceKind;          // absent on older payloads → treat as 'display'
  isDefault: boolean;
  archivedAt: string | null;
  createdAt: string;
  content: DeviceContent | null;
  // ── sharing ──
  // ownerId always travels: compare it to your own user_id to tell an owned
  // device from one shared with you. ownerEmail is set only on devices shared
  // *to* you (who shared it). sharedWith is your grantee list — set only on
  // your own devices, never exposed to grantees.
  ownerId?: number;
  ownerEmail?: string | null;
  sharedWith?: string[] | null;
}

// Lightweight listing — no content bodies (the agent's list?view=summary shape).
export interface DeviceSummary {
  id: string;
  name: string;
  description?: string | null;
  kind?: DeviceKind;
  isDefault: boolean;
  archivedAt: string | null;
  contentType: ContentType | null;
  contentUpdatedAt: string | null;
  createdAt: string;
}

// ── Memories ──
export type MemoryCategory = 'user' | 'project' | 'reference' | 'feedback' | 'note';

export interface Memory {
  key: string;
  category: MemoryCategory;
  description?: string | null;
  body: string;
  createdAt?: string | null;
  updatedAt?: string | null;
}

// Recall listing — no body (the agent's list/search shape).
export interface MemorySummary {
  key: string;
  category: MemoryCategory;
  description?: string | null;
  updatedAt?: string | null;
}

// ── Ledger sessions (the telemetry plane — The Ledger Book, phase 1) ──
// The wire representation from /ledger: stored facts (snake_case, matching the
// service) plus the computed display fields (activity, relevant). Both statuses
// are STORED — turn_state (rev 17) and the lifecycle status (rev 18).
// Three states, no fourth (rev 20 retired 'expired' and the sweep).
export type LedgerStatus = 'active' | 'dormant' | 'archived';
export type LedgerActivity = 'waiting' | 'processing' | 'run' | null;

export interface LedgerSession {
  id: string;
  workspace_id: string | null;
  machine: string | null;
  label: string | null;
  turn_state: 'waiting' | 'processing';  // stored — set by prompt/Stop signals

  first_seen: string | null;
  last_event_at: string | null;
  last_prompt_at: string | null;
  last_stop_at: string | null;
  last_run_at: string | null;
  ended_at: string | null;
  ever_prompted: boolean;
  archived_at: string | null;
  status: LedgerStatus;       // stored — one writer per transition (rev 18)
  stream_id: string | null;   // computed — board attribution (rev 19), never stored
  activity: LedgerActivity;   // computed — active sessions' glyph only
  relevant: boolean;          // computed — the board filter
}

// The record plane (rev 19): immutable events + managed streams.
export interface LedgerEvent {
  id: string;
  at: string;
  stream_id: string;
  headline: string;
  body: string[];
  session_id: string | null;
}

export interface LedgerStream {
  id: string;                 // the slug
  title: string | null;
  state: string | null;
  next_action: string | null;
  open_loops: string[];
  working_paths: string[];
  since: string | null;
  updated: string | null;
  closed_at: string | null;
  staleness: 'fresh' | 'aging' | 'stale' | null;  // computed — null when closed
}

// GET /ledger/board — the data structure the board view renders.
// Sessions (ordering guaranteed server-side), recent events, active streams.
// Products are absent by decision — deferred to a later phase.
export interface LedgerBoard {
  sessions: LedgerSession[];
  events: LedgerEvent[];
  streams: LedgerStream[];
  as_of: string;
}

// ── Content body shapes (frontend-only — parsed from DeviceContent.body JSON) ──
export interface ListItem {
  text: string;
  checked?: boolean;
}

export interface DashboardCard {
  title: string;
  value: string;
  subtitle?: string;
}

export interface TableColumn {
  id: string;
  label: string;
}

export interface TableData {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
}

// ── WebSocket events (frontend-only — emitted by backend/websocket.py broadcasts) ──
export type WSEvent =
  | { event: 'device_created'; device: Device }
  | { event: 'device_updated'; device: Device }
  | { event: 'device_deleted'; deviceId: string }
  | { event: 'device_archived'; deviceId: string }
  | { event: 'device_unarchived'; device: Device }
  | { event: 'device_shared'; device: Device }      // a device was shared with me
  | { event: 'device_unshared'; deviceId: string }  // my access to a shared device was revoked
  | { event: 'devices_reset' }
  | { event: 'ledger_sessions' };                   // any ledger session changed — refetch the board
