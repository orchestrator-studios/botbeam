import { get, post, patch, del } from './index';
import { settings } from '../../config/settings';
import type { Device, User } from '../../types';

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
  createDevice: (name: string): Promise<Device> => post<Device>('/api/devices', { name }),
  renameDevice: (id: string, name: string): Promise<Device> =>
    patch<Device>(`/api/devices/${id}`, { name }),
  archiveDevice: (id: string): Promise<Device> => post<Device>(`/api/devices/${id}/archive`),
  unarchiveDevice: (id: string): Promise<Device> => post<Device>(`/api/devices/${id}/unarchive`),
  deleteDevice: (id: string): Promise<void> => del(`/api/devices/${id}`),
  resetDevices: (): Promise<void> => del('/api/devices'),

  proxyUrl: (url: string): string => `${settings.apiUrl}/api/proxy?url=${encodeURIComponent(url)}`,
};
