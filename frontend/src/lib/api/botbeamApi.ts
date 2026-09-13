import { get, post, patch, put, del, delJson } from './index';
import { settings } from '../../config/settings';
import type { Device, User, Memory, MemorySummary, MemoryCategory, LedgerBoard, LedgerSession, LedgerStream, LedgerDeliverable } from '../../types';

// ── request/response wrappers (specific to these endpoints, not domain objects;
// names mirror backend/routers/auth.py) ──
export interface AuthResponse extends User {
  access_token: string;
  token_type: string;
}

export interface AgentTokenResponse {
  access_token: string;
  token_type: string;
  name: string;
}

export const botbeamApi = {
  // ── Auth (JWT bearer — house pattern) ──
  me: (): Promise<User> => get<User>('/auth/me'),
  register: (email: string, password: string): Promise<AuthResponse> =>
    post<AuthResponse>('/auth/register', { email, password }),
  login: (email: string, password: string): Promise<AuthResponse> =>
    post<AuthResponse>('/auth/login', { email, password }),

  // Long-lived token for the agent / orchestra skill (saved to a creds file)
  createAgentToken: (): Promise<AgentTokenResponse> =>
    post<AgentTokenResponse>('/auth/agent-token', { name: 'orchestra' }),

  // ── Devices (namespace resolved server-side from the token) ──
  getDevices: (): Promise<Device[]> => get<Device[]>('/api/devices'),
  // Single device by id — returns archived devices too (used by the pinned view).
  getDevice: (id: string): Promise<Device> => get<Device>(`/api/devices/${id}`),
  getArchivedDevices: (): Promise<Device[]> => get<Device[]>('/api/devices?archived=true'),
  // beam_new — create a new entry (browser sends name only; the agent/skill may include content)
  beamNew: (name: string): Promise<Device> => post<Device>('/api/devices', { name }),
  renameDevice: (id: string, name: string): Promise<Device> =>
    patch<Device>(`/api/devices/${id}`, { name }),
  archiveDevice: (id: string): Promise<Device> => post<Device>(`/api/devices/${id}/archive`),
  unarchiveDevice: (id: string): Promise<Device> => post<Device>(`/api/devices/${id}/unarchive`),
  deleteDevice: (id: string): Promise<void> => del(`/api/devices/${id}`),
  resetDevices: (): Promise<void> => del('/api/devices'),

  // ── Memories (durable typed facts; recalled by list / get / text search) ──
  getMemories: (q?: string, category?: string): Promise<MemorySummary[]> => {
    const p = new URLSearchParams();
    if (q) p.set('q', q);
    if (category) p.set('category', category);
    const qs = p.toString();
    return get<MemorySummary[]>(`/api/memories${qs ? `?${qs}` : ''}`);
  },
  getMemory: (key: string): Promise<Memory> => get<Memory>(`/api/memories/${encodeURIComponent(key)}`),
  putMemory: (
    key: string,
    payload: { category?: MemoryCategory; description?: string; body: string },
  ): Promise<Memory> => put<Memory>(`/api/memories/${encodeURIComponent(key)}`, payload),
  deleteMemory: (key: string): Promise<void> => del(`/api/memories/${encodeURIComponent(key)}`),
  resetMemories: (): Promise<void> => del('/api/memories'),

  // ── Sharing (view-only grants to other accounts) ──
  getSharedDevices: (): Promise<Device[]> => get<Device[]>('/api/devices/shared'),
  shareDevice: (id: string, email: string): Promise<Device> =>
    post<Device>(`/api/devices/${id}/shares`, { email }),
  unshareDevice: (id: string, email: string): Promise<Device> =>
    delJson<Device>(`/api/devices/${id}/shares?email=${encodeURIComponent(email)}`),

  // ── Ledger sessions (the board's data structure; statuses stored server-side) ──
  getLedgerBoard: (): Promise<LedgerBoard> => get<LedgerBoard>('/ledger/board'),
  archiveSession: (id: string): Promise<LedgerSession> =>
    post<LedgerSession>(`/ledger/sessions/${encodeURIComponent(id)}/archive`),
  unarchiveSession: (id: string): Promise<LedgerSession> =>
    post<LedgerSession>(`/ledger/sessions/${encodeURIComponent(id)}/unarchive`),
  archiveAllDormant: (keep?: string[]): Promise<{ items: LedgerSession[] }> =>
    post<{ items: LedgerSession[] }>('/ledger/sessions/archive', { all: true, keep }),

  // ── Board-initiated record-plane acts (invariant 11) ──
  // The board is an actor like a session is: every write names who did it, in
  // one field. From here that is always "board" — the user acting at the
  // interface. Closing and retiring each log an event carrying it.
  closeStream: (id: string, reason: string): Promise<{ stream: LedgerStream }> =>
    post<{ stream: LedgerStream }>(
      `/ledger/streams/${encodeURIComponent(id)}/close`, { reason, actor: 'board' }),
  reopenStream: (id: string, reason: string): Promise<{ stream: LedgerStream }> =>
    post<{ stream: LedgerStream }>(
      `/ledger/streams/${encodeURIComponent(id)}/reopen`, { reason, actor: 'board' }),
  retireDeliverable: (id: string): Promise<LedgerDeliverable> =>
    post<LedgerDeliverable>(
      `/ledger/deliverables/${encodeURIComponent(id)}/retire`, { actor: 'board' }),
  unretireDeliverable: (id: string): Promise<LedgerDeliverable> =>
    post<LedgerDeliverable>(
      `/ledger/deliverables/${encodeURIComponent(id)}/unretire`, { actor: 'board' }),

  proxyUrl: (url: string): string => `${settings.apiUrl}/api/proxy?url=${encodeURIComponent(url)}`,
};
