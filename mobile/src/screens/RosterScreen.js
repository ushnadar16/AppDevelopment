import React, { useCallback, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { newId } from '../storage';
import { Badge, Btn, C, Card, Chip, Empty, Field, H2, Loading, Muted, Notice, s } from '../ui';

const today = () => new Date().toISOString().slice(0, 10);
const ACTIONS = [['transfer', 'Transfer'], ['loan', 'Loan'], ['release', 'Release']];

export default function RosterScreen() {
  const { session, online, enqueue } = useApp();
  const own = session.user.club_id;
  const [data, setData] = useState(null);
  const [player, setPlayer] = useState(null);
  const [type, setType] = useState('transfer');
  const [to, setTo] = useState(null);
  const [date, setDate] = useState(today());
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getCached(`/api/v1/roster/squads?club_id=${own || ''}`).then((r) => setData({ ...r.data, offline: r.offline }))
      .catch((e) => setMsg(['bad', errorText(e)]));
  }, [own]);
  useFocusEffect(load);

  if (!data) return msg ? <Notice kind={msg[0]} text={msg[1]} /> : <Loading text="Loading roster…" />;
  const mine = data.squads.find((q) => q.club_id === own) || data.squads[0];
  const others = data.squads.filter((q) => q !== mine);
  if (!mine) return <Empty text="Your club has no squad registered in a league yet." />;

  const body = () => ({
    request_id: newId('req'), league_id: data.league_id, player_id: player.player_id, type,
    from_squad_id: mine.squad_id, to_squad_id: type === 'release' ? null : to,
    effective_date: date, loan_end_date: type === 'loan' ? end : null,
    reason: reason || `${type} via app`, requested_by: session.user.user_id,
  });

  const submit = () => {
    if (!player) return setMsg(['warn', 'Choose a player first.']);
    if (type !== 'release' && !to) return setMsg(['warn', 'Choose the destination squad.']);
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
      enqueue('roster_transfer', b, player.audit_count, label);
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
      {data.offline ? <Notice kind="warn" text="Offline — changes will be queued and synced later." /> : null}
      {msg ? <Notice kind={msg[0]} text={msg[1]} /> : null}
      <Card>
        <H2>1. Choose a player — {mine.name}</H2>
        {mine.players.length === 0 ? <Muted>No players in this squad.</Muted> : null}
        {mine.players.map((p) => (
          <Chip key={p.player_id} label={`${p.name} · ${p.position.toUpperCase()}${p.registration_type === 'loan' ? ' · on loan' : ''}`}
            selected={player && player.player_id === p.player_id} onPress={() => setPlayer(p)} />
        ))}
      </Card>
      <Card>
        <H2>2. Action</H2>
        <View style={s.wrap}>{ACTIONS.map(([k, l]) => <Chip key={k} label={l} selected={type === k} onPress={() => setType(k)} />)}</View>
        {type !== 'release' ? <>
          <Muted style={{ marginVertical: 6 }}>Destination squad</Muted>
          <View style={s.wrap}>{others.map((q) => <Chip key={q.squad_id} label={q.name} selected={to === q.squad_id} onPress={() => setTo(q.squad_id)} />)}</View>
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
