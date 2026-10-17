import React, { useCallback, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getCached } from '../api';
import { useApp } from '../AppContext';
import { errorText } from '../messages';
import { C, Card, Chip, Empty, H1, H2, Loading, Muted, Notice, P, s } from '../ui';

export default function ClubScreen() {
  const { session } = useApp();
  const [clubs, setClubs] = useState(null);
  const [clubId, setClubId] = useState(session.user.club_id || null);
  const [club, setClub] = useState(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState('');

  useFocusEffect(useCallback(() => {
    getCached('/api/v1/clubs').then((r) => {
      setClubs(r.data.clubs);
      const id = clubId || (r.data.clubs[0] && r.data.clubs[0].club_id);
      setClubId(id);
      if (id) return getCached(`/api/v1/clubs/${id}`).then((c) => { setClub(c.data); setOffline(c.offline || r.offline); setError(''); });
    }).catch((e) => setError(errorText(e)));
  }, [clubId]));

  if (!clubs && !error) return <Loading text="Loading club…" />;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad}>
      <Notice kind="bad" text={error} />
      {offline ? <Notice kind="warn" text="Offline — showing the club profile saved on this phone." /> : null}
      <View style={s.wrap}>
        {(clubs || []).map((c) => <Chip key={c.club_id} label={c.name} selected={clubId === c.club_id} onPress={() => setClubId(c.club_id)} />)}
      </View>
      {club ? (
        <>
          <Card>
            <H1>{club.name}</H1>
            <Muted>{club.tenant ? club.tenant.name : ''}</Muted>
            <P style={{ marginTop: 8 }}>🏟 Home venue: {club.home_venue.name}</P>
            <Muted>Coordinates: {club.home_venue.lat}, {club.home_venue.lng}</Muted>
          </Card>
          <Card>
            <H2>Staff</H2>
            {Object.entries(club.staff || {}).map(([role, name]) => (
              <P key={role}>{role[0].toUpperCase() + role.slice(1)}: {name}</P>
            ))}
          </Card>
          <Card>
            <H2>Active roster ({club.roster.length})</H2>
            {club.roster.length === 0 ? <Empty text="No players registered yet." /> : null}
            {club.roster.map((p) => (
              <View key={p.player_id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderColor: '#E5E7EB' }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{p.name}</Text>
                <Muted>{(p.position || '').toUpperCase()} · {(p.role || '').replace('_', ' ')}</Muted>
              </View>
            ))}
          </Card>
        </>
      ) : clubId ? <Loading /> : <Empty text="No clubs to show." />}
    </ScrollView>
  );
}
