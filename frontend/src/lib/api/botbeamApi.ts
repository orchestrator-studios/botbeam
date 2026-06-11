import { get, post, patch, del } from './index';
import { settings } from '../../config/settings';
import type { Device } from '../../types';

export interface AuthResult {
  access_token: string;
  token_type: string;
  email: string;
  user_id: string;
  org_id: string;
  role: string;
  username: string;
}

export const botbeamApi = {
  // ── Auth (JWT bearer — house pattern) ──
  me: () => get<{ email: string; user_id: string; org_id: string; role: string; username: string }>('/auth/me'),
  register: (email: string, password: string) => post<AuthResult>('/auth/register', { email, password }),
  login: (email: string, password: string) => post<AuthResult>('/auth/login', { email, password }),

  // Long-lived token for the agent / orchestra skill (saved to a creds file)
  createAgentToken: () => post<{ access_token: string; name: string }>('/auth/agent-token', { name: 'orchestra' }),

  // ── Devices (namespace resolved server-side from the token) ──
  getDevices: () => get<Device[]>('/api/devices'),
  getArchivedDevices: () => get<Device[]>('/api/devices?archived=true'),
  createDevice: (name: string) => post<Device>('/api/devices', { name }),
  renameDevice: (id: string, name: string) => patch<Device>(`/api/devices/${id}`, { name }),
  archiveDevice: (id: string) => post<Device>(`/api/devices/${id}/archive`),
  unarchiveDevice: (id: string) => post<Device>(`/api/devices/${id}/unarchive`),
  deleteDevice: (id: string) => del(`/api/devices/${id}`),
  resetDevices: () => del('/api/devices'),

  proxyUrl: (url: string) => `${settings.apiUrl}/api/proxy?url=${encodeURIComponent(url)}`,
};
