import React, { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getCached } from '../api';
import { errorText } from '../messages';
import { Badge, C, Card, Empty, Loading, Muted, Notice, s, teamName } from '../ui';

const ORDER = { in_progress: 0, upcoming: 1, completed: 2 };

export default function FixturesScreen({ navigation }) {
  const [data, setData] = useState(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getCached('/api/v1/fixtures');
      setData(r.data.fixtures); setOffline(r.offline); setError('');
    } catch (e) { setError(errorText(e)); }
  }, []);

  useFocusEffect(useCallback(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]));

  if (!data && !error) return <Loading text="Loading fixtures…" />;
  const sorted = (data || []).slice().sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  return (
    <FlatList style={s.screen} contentContainerStyle={s.pad} data={sorted} keyExtractor={(m) => m.match_id}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      ListHeaderComponent={<>
        <Notice kind="bad" text={error} />
        {offline ? <Notice kind="warn" text="You're offline. Showing fixtures saved on this phone." /> : null}
      </>}
      ListEmptyComponent={<Empty text="No matches yet. Fixtures appear here once a league is scheduled." />}
      renderItem={({ item }) => {
        const m = { ...item, home: item.home.team_id, away: item.away.team_id, home_score: item.home.score,
          away_score: item.away.score, home_name: teamName(item.home.team_id), away_name: teamName(item.away.team_id) };
        return (
        <Pressable onPress={() => navigation.navigate('Match', { matchId: m.match_id, title: `${m.home_name || m.home} vs ${m.away_name || m.away}` })}
          accessibilityRole="button"
          accessibilityLabel={`${m.home_name || m.home} ${m.home_score}, ${m.away_name || m.away} ${m.away_score}, ${m.status.replace('_', ' ')}. Open match.`}>
          <Card>
            <View style={[s.row, { justifyContent: 'space-between', marginBottom: 8 }]}>
              <Badge status={m.status} />
              <Muted>{m.scheduled_at ? new Date(m.scheduled_at).toLocaleString() : (m.league_id || 'Friendly')}</Muted>
            </View>
            <View style={[s.row, { justifyContent: 'space-between' }]}>
              <Text style={{ fontSize: 17, fontWeight: '600', color: C.text, flex: 1 }}>{m.home_name || m.home}</Text>
              <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, marginHorizontal: 12 }}>
                {m.status === 'upcoming' ? 'vs' : `${m.home_score} – ${m.away_score}`}
              </Text>
              <Text style={{ fontSize: 17, fontWeight: '600', color: C.text, flex: 1, textAlign: 'right' }}>{m.away_name || m.away}</Text>
            </View>
            {m.venue ? <Muted style={{ marginTop: 6 }}>📍 {m.venue}</Muted> : null}
          </Card>
        </Pressable>
        );
      }} />
  );
}
