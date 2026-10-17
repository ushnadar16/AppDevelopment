import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getCached } from '../api';
import { errorText } from '../messages';
import { Badge, C, Card, Chip, Empty, H2, Loading, Muted, Notice, s } from '../ui';

const COLS = [['P', 'played'], ['W', 'won'], ['D', 'drawn'], ['L', 'lost'], ['+/-', 'diff'], ['Pts', 'points']];

export default function StandingsScreen({ navigation }) {
  const [leagues, setLeagues] = useState(null);
  const [league, setLeague] = useState(null);
  const [table, setTable] = useState(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState('');

  useFocusEffect(useCallback(() => {
    getCached('/api/v1/leagues').then((r) => {
      setLeagues(r.data.leagues); setOffline(r.offline);
      if (!league && r.data.leagues.length) setLeague(r.data.leagues[0].league_id);
    }).catch((e) => setError(errorText(e)));
  }, [league]));

  useEffect(() => {
    if (!league) return;
    getCached(`/api/v1/standings/${league}`).then((r) => { setTable(r.data); setOffline(r.offline); setError(''); })
      .catch((e) => setError(errorText(e)));
  }, [league]);

  if (!leagues && !error) return <Loading text="Loading leagues…" />;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad}>
      <Notice kind="bad" text={error} />
      {offline ? <Notice kind="warn" text="Offline — showing standings saved on this phone." /> : null}
      {leagues && leagues.length === 0 ? <Empty text="No leagues yet." /> : null}
      <View style={s.wrap}>
        {(leagues || []).map((l) => <Chip key={l.league_id} label={l.league_id} selected={league === l.league_id} onPress={() => setLeague(l.league_id)} />)}
      </View>
      {table ? (
        <Card>
          <H2>Table · top {table.qualification_spots} qualify</H2>
          <ScrollView horizontal>
            <View>
              <View style={[s.row, { borderBottomWidth: 2, borderColor: C.border, paddingVertical: 8 }]}>
                <Text style={[cell, { width: 28 }]}>#</Text>
                <Text style={[cell, { width: 140, textAlign: 'left' }]}>Team</Text>
                {COLS.map(([h]) => <Text key={h} style={cell}>{h}</Text>)}
                <Text style={[cell, { width: 130 }]}>Status</Text>
              </View>
              {table.table.map((r) => (
                <View key={r.team_id} style={[s.row, { paddingVertical: 10, borderBottomWidth: 1, borderColor: '#E5E7EB',
                  backgroundColor: r.rank <= table.qualification_spots ? '#ECFDF5' : 'transparent' }]}
                  accessible accessibilityLabel={`Rank ${r.rank}, ${table.team_names?.[r.team_id] || r.team_id}, ${r.points} points, ${r.status.replace('_', ' ')}`}>
                  <Text style={[cell, { width: 28, fontWeight: '800' }]}>{r.rank}</Text>
                  <Text style={[cell, { width: 140, textAlign: 'left' }]} numberOfLines={1}>{table.team_names?.[r.team_id] || r.team_id}</Text>
                  {COLS.map(([h, k]) => <Text key={h} style={[cell, h === 'Pts' && { fontWeight: '800' }]}>{r[k]}</Text>)}
                  <View style={{ width: 130, paddingLeft: 8 }}><Badge status={r.status} /></View>
                </View>
              ))}
            </View>
          </ScrollView>
          <Muted style={{ marginTop: 8 }}>Green rows are in qualification places. Tap Fixtures to open a match.</Muted>
        </Card>
      ) : league ? <Loading text="Loading table…" /> : null}
    </ScrollView>
  );
}

const cell = { width: 44, textAlign: 'center', fontSize: 15, color: C.text };
