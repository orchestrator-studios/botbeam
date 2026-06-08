import { settings } from '../../config/settings';
import { getToken } from '../authStorage';

// Every request carries the JWT as `Authorization: Bearer <token>` (house pattern).
function withAuth(extra?: Record<string, string>): Record<string, string> {
  const t = getToken();
  return { ...(extra || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${settings.apiUrl}${url}`, {
    ...init,
    headers: withAuth(init?.headers as Record<string, string> | undefined),
  });
  if (!res.ok) {
    const err = new Error(`${init?.method || 'GET'} ${url} failed: ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const get = <T>(url: string) => req<T>(url);

export const post = <T>(url: string, body?: unknown) =>
  req<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

export const patch = <T>(url: string, body: unknown) =>
  req<T>(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const del = async (url: string): Promise<void> => {
  const res = await fetch(`${settings.apiUrl}${url}`, { method: 'DELETE', headers: withAuth() });
  if (!res.ok && res.status !== 404) {
    const err = new Error(`DELETE ${url} failed: ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
};
