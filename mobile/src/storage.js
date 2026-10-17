// Local persistence: SQLite cache + persistent offline action queue (NFR-4),
// SecureStore (Android Keystore) for the auth token (NFR-5).
import * as SQLite from 'expo-sqlite';
import * as SecureStore from 'expo-secure-store';

const db = SQLite.openDatabaseSync('nascon.db');
db.execSync(`
  CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS queue (action_id TEXT PRIMARY KEY NOT NULL, type TEXT NOT NULL, label TEXT,
    payload TEXT NOT NULL, base_version INTEGER NOT NULL, queued_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS sync_results (action_id TEXT PRIMARY KEY NOT NULL, label TEXT, status TEXT,
    message TEXT, at TEXT);
`);

export function cacheSet(key, data) {
  db.runSync('INSERT OR REPLACE INTO cache (key, json, updated_at) VALUES (?, ?, ?)',
    [key, JSON.stringify(data), new Date().toISOString()]);
}

export function cacheGet(key) {
  const row = db.getFirstSync('SELECT json, updated_at FROM cache WHERE key = ?', [key]);
  return row ? { data: JSON.parse(row.json), updatedAt: row.updated_at } : null;
}

export function nowStamp() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function newId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// Actions are stored in exactly the /offline-sync format (Section 5.14).
export function enqueue(type, payload, baseVersion, label) {
  const action = { action_id: newId('act'), type, queued_at: nowStamp(), base_version: baseVersion, payload };
  db.runSync('INSERT INTO queue (action_id, type, label, payload, base_version, queued_at) VALUES (?, ?, ?, ?, ?, ?)',
    [action.action_id, type, label || type, JSON.stringify(payload), baseVersion, action.queued_at]);
  return action;
}

export function listQueue() {
  return db.getAllSync('SELECT * FROM queue ORDER BY queued_at ASC').map((r) => ({
    action_id: r.action_id, type: r.type, label: r.label, queued_at: r.queued_at,
    base_version: r.base_version, payload: JSON.parse(r.payload),
  }));
}

export function removeFromQueue(actionId) {
  db.runSync('DELETE FROM queue WHERE action_id = ?', [actionId]);
}

export function saveResult(r) {
  db.runSync('INSERT OR REPLACE INTO sync_results (action_id, label, status, message, at) VALUES (?, ?, ?, ?, ?)',
    [r.action_id, r.label, r.status, r.message, new Date().toISOString()]);
}

export function listResults() {
  return db.getAllSync('SELECT * FROM sync_results ORDER BY at DESC LIMIT 30');
}

export const secure = {
  get: (k) => SecureStore.getItemAsync(k),
  set: (k, v) => SecureStore.setItemAsync(k, v),
  del: (k) => SecureStore.deleteItemAsync(k),
};
