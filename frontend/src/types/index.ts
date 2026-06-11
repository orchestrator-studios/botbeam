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
  | { event: 'devices_reset' };
