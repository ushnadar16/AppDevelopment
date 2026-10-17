import React, { useCallback, useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { cacheGet, newId } from '../storage';
import { Btn, Card, Chip, Empty, Field, H2, Loading, Muted, Notice, s, teamName } from '../ui';

const today = () => new Date().toISOString().slice(0, 10);
const ACTIONS = [['transfer', 'Transfer'], ['loan', 'Loan'], ['release', 'Release']];
const TENANT_CLUBS = ['club-alpha-1', 'club-alpha-2'];

export default function RosterScreen() {
  const { session, online, enqueue } = useApp();
  const own = session.user.club_id || 'club-alpha-1';
  const [club, setClub] = useState(null);
  const [offline, setOffline] = useState(false);
  const [player, setPlayer] = useState(null);
  const [type, setType] = useState('transfer');
  const [to, setTo] = useState(null);
  const [date, setDate] = useState(today());
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getCached(`/api/v1/clubs/${own}`).then((r) => {
      setClub(r.data); setOffline(r.offline);
      // prefetch each player's audit history so offline actions carry the right base_version
      if (!r.offline) r.data.roster.forEach((p) => getCached(`/api/v1/roster/history/${p.player_id}`).catch(() => {}));
    }).catch((e) => setMsg(['bad', errorText(e)]));
  }, [own]);
  useFocusEffect(load);

  if (!club) return msg ? <Notice kind={msg[0]} text={msg[1]} /> : <Loading text="Loading roster…" />;
  const others = TENANT_CLUBS.filter((c) => c !== own);
  const leagueId = club.roster_league_id || 'league-alpha-1';

  const auditCount = (pid) => {
    const h = cacheGet(`/api/v1/roster/history/${pid}`);
    return h && h.data && Array.isArray(h.data.history) ? h.data.history.length : 0;
  };

  const body = () => ({
    request_id: newId('req'), league_id: leagueId, player_id: player.player_id, type,
    from_squad_id: own, to_squad_id: type === 'release' ? null : to,
    effective_date: date, loan_end_date: type === 'loan' ? end : null,
    reason: reason || `${type} via app`, requested_by: session.user.user_id,
  });

  const submit = () => {
    if (!player) return setMsg(['warn', 'Choose a player first.']);
    if (type !== 'release' && !to) return setMsg(['warn', 'Choose the destination club.']);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return setMsg(['warn', 'Enter the date as YYYY-MM-DD.']);
    if (type === 'loan' && !/^\d{4}-\d{2}-\d{2}$/.test(end)) return setMsg(['warn', 'Enter the loan end date as YYYY-MM-DD.']);
    Alert.alert(`Confirm ${type}`, `${type[0].toUpperCase() + type.slice(1)} ${player.name}?`, [
      { text: 'Cancel', style: 'cancel' }, { text: 'Confirm', onPress: run },
    ]);
  };

  const run = async () => {
    const b = body();
    const label = `${type} ${player.name}`;
    if (!online) {
      enqueue('roster_transfer', b, auditCount(player.player_id), label);
      setMsg(['warn', `Saved on this phone: "${label}" is pending and will sync when you're back online.`]);
      setPlayer(null);
      return;
    }
    setBusy(true); setMsg(null);
    try {
      const r = await api.transfer(b);
      setMsg(['ok', r.state === 'deferred_until_match_end'
        ? `${player.name}: accepted. Takes effect after the match in progress ends.` : `${player.name}: ${type} done.`]);
      setPlayer(null); load();
    } catch (e) { setMsg(['bad', errorText(e)]); } finally { setBusy(false); }
  };

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad} keyboardShouldPersistTaps="handled">
      {offline ? <Notice kind="warn" text="Offline — changes will be saved on this phone and synced later." /> : null}
      {msg ? <Notice kind={msg[0]} text={msg[1]} /> : null}
      <Card>
        <H2>1. Choose a player — {club.name}</H2>
        {club.roster.length === 0 ? <Empty text="No players in this squad yet." /> : null}
        <View style={s.wrap}>
          {club.roster.map((p) => (
            <Chip key={p.player_id} label={`${p.name} · ${p.position.toUpperCase()}${p.registration_type === 'loan' ? ' · on loan' : ''}`}
              selected={player && player.player_id === p.player_id} onPress={() => setPlayer(p)} />
          ))}
        </View>
      </Card>
      <Card>
        <H2>2. Action</H2>
        <View style={s.wrap}>{ACTIONS.map(([k, l]) => <Chip key={k} label={l} selected={type === k} onPress={() => setType(k)} />)}</View>
        {type !== 'release' ? <>
          <Muted style={{ marginVertical: 6 }}>Destination club</Muted>
          <View style={s.wrap}>{others.map((c) => <Chip key={c} label={teamName(c)} selected={to === c} onPress={() => setTo(c)} />)}</View>
        </> : null}
        <Field label="Effective date (YYYY-MM-DD)" value={date} onChangeText={setDate} />
        {type === 'loan' ? <Field label="Loan end date (YYYY-MM-DD)" value={end} onChangeText={setEnd} placeholder="2026-12-31" /> : null}
        <Field label="Reason" value={reason} onChangeText={setReason} placeholder="Tactical move" />
        <Btn title={busy ? 'Saving…' : online ? 'Submit' : 'Save offline'} onPress={submit} disabled={busy}
          kind={type === 'release' ? 'danger' : 'primary'} />
      </Card>
    </ScrollView>
  );
}
