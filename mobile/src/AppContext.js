import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { api, setBase, setToken, getBase, DEFAULT_SERVER } from './api';
import { enqueue as dbEnqueue, listQueue, listResults, newId, removeFromQueue, saveResult, secure } from './storage';
import { explain } from './messages';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

import { EMERALD, IVORY } from './theme';
const DEFAULT_THEME = { primary: EMERALD, secondary: IVORY };

export function AppProvider({ children }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState(null); // { user, tenant }
  const [server, setServerState] = useState(DEFAULT_SERVER);
  const [online, setOnline] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [queue, setQueue] = useState([]);
  const [results, setResults] = useState([]);
  const deviceId = useRef(null);
  const syncingRef = useRef(false);

  useEffect(() => {
    (async () => {
      const s = await secure.get('server');
      if (s) { setBase(s); setServerState(s); }
      let dev = await secure.get('device_id');
      if (!dev) { dev = newId('dev'); await secure.set('device_id', dev); }
      deviceId.current = dev;
      // Always start at the login screen: drop any session from a previous launch.
      await secure.del('token');
      await secure.del('session');
      setQueue(listQueue());
      setResults(listResults());
      setReady(true);
    })();
  }, []);

  const check = useCallback(async () => {
    const ok = await api.health();
    setOnline(ok);
    return ok;
  }, []);

  useEffect(() => {
    check();
    const id = setInterval(check, 5000);
    const unsub = NetInfo.addEventListener(() => { check(); });
    return () => { clearInterval(id); unsub(); };
  }, [check, server]);

  const syncNow = useCallback(async () => {
    if (syncingRef.current) return;
    const pending = listQueue();
    if (!pending.length) return;
    syncingRef.current = true;
    setSyncing(true);
    try {
      const res = await api.offlineSync({
        device_id: deviceId.current,
        actions: pending.map(({ action_id, type, queued_at, base_version, payload }) =>
          ({ action_id, type, queued_at, base_version, payload })),
      });
      res.results.forEach((r) => {
        const item = pending.find((p) => p.action_id === r.action_id);
        let message;
        if (r.status === 'applied') message = r.resolution === 'rebased_append'
          ? 'Saved. Others had made changes too, so it was added on top of the latest data.' : 'Saved.';
        else if (r.status === 'duplicate') message = 'Already saved earlier, skipped.';
        else message = explain(r.error_code);
        saveResult({ action_id: r.action_id, label: item ? item.label : r.action_id, status: r.status, message });
        removeFromQueue(r.action_id);
      });
    } catch (e) {
      // still offline or server error: keep the queue for the next attempt
    } finally {
      syncingRef.current = false;
      setSyncing(false);
      setQueue(listQueue());
      setResults(listResults());
    }
  }, []);

  useEffect(() => {
    if (online && session && queue.length) syncNow();
  }, [online, session, queue.length, syncNow]);

  const enqueue = useCallback((type, payload, baseVersion, label) => {
    const a = dbEnqueue(type, payload, baseVersion, label);
    setQueue(listQueue());
    return a;
  }, []);

  const login = useCallback(async (email, password) => {
    try {
      const res = await api.login(email, password);
      setToken(res.token);
      const sess = { user: res.user, tenant: res.tenant || res.user.tenant || null };
      await secure.set('token', res.token);
      await secure.set('session', JSON.stringify(sess));
      // remembered (in the Android Keystore) so the same user can sign in again while offline
      await secure.set('offline_login', JSON.stringify({ email, password, token: res.token, session: sess }));
      setSession(sess);
      return { offline: false };
    } catch (e) {
      if (e.status !== 0) throw e;
      const saved = await secure.get('offline_login');
      const o = saved ? JSON.parse(saved) : null;
      if (o && o.email === email && o.password === password) {
        setToken(o.token);
        setSession(o.session);
        return { offline: true };
      }
      throw e;
    }
  }, []);

  const logout = useCallback(async () => {
    setToken(null);
    await secure.del('token');
    await secure.del('session');
    setSession(null);
  }, []);

  const setServer = useCallback(async (url) => {
    setBase(url);
    const clean = getBase();
    await secure.set('server', clean);
    setServerState(clean);
    check();
  }, [check]);

  const theme = { ...DEFAULT_THEME, brand: (session && session.tenant && session.tenant.colors) || null };
  const status = syncing ? 'syncing' : online ? 'online' : 'offline';

  return (
    <Ctx.Provider value={{ ready, session, login, logout, server, setServer, online, status, syncing,
      queue, results, enqueue, syncNow, theme, refreshStatus: check }}>
      {children}
    </Ctx.Provider>
  );
}
