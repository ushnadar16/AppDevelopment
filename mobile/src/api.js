import { cacheGet, cacheSet } from './storage';

// Emulator: http://10.0.2.2:8080 — phone: http://<laptop LAN IP>:8080 (changeable in Account > Server).
export const DEFAULT_SERVER = 'http://10.0.2.2:8080';
let BASE = DEFAULT_SERVER;
let TOKEN = null;

export const setBase = (u) => { BASE = (u || DEFAULT_SERVER).trim().replace(/\/+$/, ''); };
export const getBase = () => BASE;
export const setToken = (t) => { TOKEN = t; };
export const getToken = () => TOKEN;

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message || code);
    this.status = status; this.code = code; this.details = details || {};
  }
}

async function request(method, path, body, timeout = 8000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the server.');
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    const err = (data && data.error) || {};
    throw new ApiError(res.status, err.code || `HTTP_${res.status}`, err.message, err.details);
  }
  return data;
}

// Network first, fall back to the local SQLite cache when offline.
export async function getCached(path) {
  try {
    const data = await request('GET', path);
    cacheSet(path, data);
    return { data, offline: false };
  } catch (e) {
    if (e.status === 0) {
      const c = cacheGet(path);
      if (c) return { data: c.data, offline: true, updatedAt: c.updatedAt };
    }
    throw e;
  }
}

export const api = {
  health: async () => { try { await request('GET', '/health', undefined, 3000); return true; } catch (e) { return false; } },
  login: (email, password) => request('POST', '/api/v1/auth/login', { email, password }),
  postEvent: (body) => request('POST', '/api/v1/events', body),
  transfer: (body) => request('POST', '/api/v1/roster/transfer', body),
  checkout: (body) => request('POST', '/api/v1/checkout', body, 15000),
  offlineSync: (body) => request('POST', '/api/v1/offline-sync', body, 15000),
};
