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
    // Surface the server's message: FastAPI returns {detail: string} or, for
    // validation errors, {detail: [{msg, loc, ...}]}.
    let detail: string | undefined;
    try {
      const data = await res.json();
      const d = (data as { detail?: unknown }).detail;
      if (typeof d === 'string') {
        detail = d;
      } else if (Array.isArray(d)) {
        detail = d
          .map((e) => (e && typeof e === 'object' && 'msg' in e ? (e as { msg: string }).msg : String(e)))
          .join('; ');
      }
    } catch {
      /* no JSON body */
    }
    const err = new Error(detail || `Request failed (${res.status})`) as Error & { status?: number; detail?: string };
    err.status = res.status;
    err.detail = detail;
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

export const put = <T>(url: string, body?: unknown) =>
  req<T>(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

export const del = async (url: string): Promise<void> => {
  const res = await fetch(`${settings.apiUrl}${url}`, { method: 'DELETE', headers: withAuth() });
  if (!res.ok && res.status !== 404) {
    const err = new Error(`DELETE ${url} failed: ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
};

// DELETE that returns a body and surfaces the server's error message (via req) —
// used where the endpoint responds with content, e.g. unshare returns the device.
export const delJson = <T>(url: string) => req<T>(url, { method: 'DELETE' });
