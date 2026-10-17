import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { Badge, Btn, C, Card, H2, Loading, Muted, Notice, money, s, teamName } from '../ui';

const label = (e) => {
  const p = e.payload || {};
  switch (e.type) {
    case 'match_init': return 'Match created';
    case 'match_start': return 'Kick-off';
    case 'match_end': return 'Full time';
    case 'score': return `${(p.event_type || '').replace(/_/g, ' ')} — ${teamName(p.team_id)}`;
    case 'discipline': return `Discipline ${p.points} — ${p.team_id}`;
    case 'tiebreak_winner': return `Tie-break won by ${p.team_id}`;
    case 'compensation': return `Correction: ${p.reason || 'event reversed'}`;
    default: return e.type;
  }
};

export default function MatchScreen({ route, navigation }) {
  const { matchId } = route.params;
  const { session, theme } = useApp();
  const [m, setM] = useState(null);
  const [product, setProduct] = useState(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await getCached(`/api/v1/matches/${matchId}`);
      setM(r.data); setOffline(r.offline); setError('');
    } catch (e) { setError(errorText(e)); }
  }, [matchId]);

  // live score: refresh every 3 s while the screen is open
  useFocusEffect(useCallback(() => { load(); const id = setInterval(load, 3000); return () => clearInterval(id); }, [load]));
  useEffect(() => { if (m) setProduct(m.pinned_product || null); }, [m]);

  if (!m) return error ? <Notice kind="bad" text={error} /> : <Loading text="Loading match…" />;
  const isOrganizer = ['league_organizer', 'super_admin'].includes(session.user.role);
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad}>
      {offline ? <Notice kind="warn" text="Offline — this is the last saved score." /> : null}
      <Card>
        <Badge status={m.status} />
        <View style={[s.row, { justifyContent: 'space-between', marginTop: 12 }]}
          accessible accessibilityLabel={`Score ${m.home.team_id} ${m.home.score}, ${m.away.team_id} ${m.away.score}`}>
          <Text style={{ flex: 1, fontSize: 16, fontWeight: '600', color: C.text }}>{route.params.title?.split(' vs ')[0] || m.home.team_id}</Text>
          <Text style={{ fontSize: 40, fontWeight: '900', color: theme.primary }}>{m.home.score} – {m.away.score}</Text>
          <Text style={{ flex: 1, fontSize: 16, fontWeight: '600', color: C.text, textAlign: 'right' }}>{route.params.title?.split(' vs ')[1] || m.away.team_id}</Text>
        </View>
        {m.home.overs ? <Muted>Overs: {m.home.overs} / {m.away.overs} · Wickets: {m.home.wickets} / {m.away.wickets}</Muted> : null}
        {m.status === 'completed' ? <Muted style={{ marginTop: 8 }}>Result: {m.outcome.replace('_', ' ')}</Muted> : null}
        {isOrganizer ? <Btn title="Record score" kind="secondary" onPress={() => navigation.navigate('Scoring', { matchId })} /> : null}
      </Card>
      {product ? (
        <Card style={{ borderColor: theme.secondary, borderWidth: 2 }}>
          <Muted>Featured from the club store</Muted>
          <H2>{product.name}</H2>
          <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 8 }}>{product.variants && product.variants[0] ? money(product.variants[0].price_minor) : ''}</Text>
          <Btn title="Buy now" onPress={() => navigation.navigate('Tabs', { screen: 'Store' })} />
        </Card>
      ) : null}
      <Card>
        <H2>Timeline</H2>
        {m.events.length === 0 ? <Muted>No events yet. The timeline fills in as the match is played.</Muted> : null}
        {m.events.slice().reverse().map((e) => (
          <View key={e.event_id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderColor: '#E5E7EB' }}>
            <Text style={{ fontSize: 16, color: e.compensated ? C.muted : C.text,
              textDecorationLine: e.compensated ? 'line-through' : 'none' }}>
              {e.sequence}. {label(e)}
            </Text>
            {e.compensated ? <Muted>Reversed by a correction</Muted> : null}
          </View>
        ))}
      </Card>
    </ScrollView>
  );
}
