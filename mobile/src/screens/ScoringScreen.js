import React, { useCallback, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { newId } from '../storage';
import { Badge, Btn, C, Card, Chip, Empty, H2, Loading, Muted, Notice, s } from '../ui';

export default function ScoringScreen({ route }) {
  const { online, enqueue } = useApp();
  const [matches, setMatches] = useState(null);
  const [matchId, setMatchId] = useState(route.params?.matchId || null);
  const [match, setMatch] = useState(null);
  const [sport, setSport] = useState(null);
  const [team, setTeam] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await getCached('/api/v1/matches');
      const ms = r.data.matches.filter((m) => m.status !== 'completed');
      setMatches(ms);
      const id = matchId || (ms[0] && ms[0].match_id);
      if (!id) return;
      setMatchId(id);
      const d = await getCached(`/api/v1/matches/${id}`);
      setMatch(d.data);
      const sp = await getCached(`/api/v1/sports/${d.data.sport_id}`);
      setSport(sp.data);
      setTeam((t) => t || d.data.home.team_id);
    } catch (e) { setMsg(['bad', errorText(e)]); }
  }, [matchId]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const send = async (type, payload, label) => {
    const body = { event_id: newId('evt'), match_id: matchId, type, payload };
    if (!online) {
      enqueue('score_event', body, match.version, label);
      setMsg(['warn', `Saved on this phone: "${label}" is pending and will sync automatically.`]);
      return;
    }
    try { await api.postEvent(body); setMsg(['ok', `${label} recorded.`]); load(); }
    catch (e) { setMsg(['bad', errorText(e)]); }
  };

  const undo = (e) => Alert.alert('Reverse this event?', 'A correction is added; the original stays in the history.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Reverse', style: 'destructive', onPress: () => send('compensation', { compensates: e.event_id, reason: 'Corrected by organizer' }, 'Correction') },
  ]);

  if (!matches) return msg ? <Notice kind={msg[0]} text={msg[1]} /> : <Loading text="Loading matches…" />;
  if (!matches.length) return <Empty text="No upcoming or live matches to score." />;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad}>
      {msg ? <Notice kind={msg[0]} text={msg[1]} /> : null}
      <Card>
        <H2>Match</H2>
        <View style={s.wrap}>
          {matches.map((m) => <Chip key={m.match_id} label={`${m.home_name} vs ${m.away_name}`} selected={matchId === m.match_id}
            onPress={() => { setMatchId(m.match_id); setTeam(null); setMatch(null); }} />)}
        </View>
      </Card>
      {match && sport ? (
        <>
          <Card>
            <Badge status={match.status} />
            <Text style={{ fontSize: 32, fontWeight: '900', color: C.text, textAlign: 'center', marginVertical: 8 }}>
              {match.home.score} – {match.away.score}
            </Text>
            {match.status === 'upcoming' ? <Btn title="Start match" onPress={() => send('match_start', {}, 'Match start')} /> : null}
            {match.status === 'in_progress' ? <Btn title="End match" kind="secondary"
              onPress={() => Alert.alert('End match?', 'This sets the final result.', [{ text: 'Cancel', style: 'cancel' },
                { text: 'End match', onPress: () => send('match_end', {}, 'Match end') }])} /> : null}
          </Card>
          {match.status === 'in_progress' ? (
            <Card>
              <H2>Add score</H2>
              <View style={s.wrap}>
                {[match.home.team_id, match.away.team_id].map((t) => <Chip key={t} label={t} selected={team === t} onPress={() => setTeam(t)} />)}
              </View>
              <View style={s.wrap}>
                {Object.keys(sport.scoring_events).map((k) => (
                  <Btn key={k} small title={`+ ${k.replace(/_/g, ' ')}`} style={{ marginRight: 8 }}
                    onPress={() => send('score', { team_id: team, event_type: k }, `${k.replace(/_/g, ' ')} for ${team}`)} />
                ))}
              </View>
            </Card>
          ) : null}
          <Card>
            <H2>Recent events</H2>
            {match.events.filter((e) => ['score', 'discipline', 'tiebreak_winner'].includes(e.type)).slice(-6).reverse().map((e) => (
              <View key={e.event_id} style={[s.row, { justifyContent: 'space-between', paddingVertical: 6 }]}>
                <Text style={{ flex: 1, fontSize: 16, color: e.compensated ? C.muted : C.text, textDecorationLine: e.compensated ? 'line-through' : 'none' }}>
                  {(e.payload.event_type || e.type).replace(/_/g, ' ')} — {e.payload.team_id}
                </Text>
                {!e.compensated ? <Btn small kind="secondary" title="Undo" onPress={() => undo(e)} /> : <Muted>Reversed</Muted>}
              </View>
            ))}
          </Card>
        </>
      ) : <Loading />}
    </ScrollView>
  );
}
