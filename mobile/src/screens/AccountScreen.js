import React, { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useApp } from '../AppContext';
import { Badge, Btn, C, Card, Field, H1, H2, Muted, Notice, P, s } from '../ui';

const ROLE = { super_admin: 'Platform Super-Admin', league_organizer: 'League Organizer', club_manager: 'Club Manager',
  player: 'Player', viewer: 'General Viewer' };

export default function AccountScreen() {
  const { session, logout, server, setServer, status, queue, results, syncNow } = useApp();
  const [srv, setSrv] = useState(server);
  const [saved, setSaved] = useState('');
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.pad} keyboardShouldPersistTaps="handled">
      <Card>
        <H1>{ROLE[session.user.role]}</H1>
        <P>{session.user.email}</P>
        {session.tenant ? <Muted>{session.tenant.name}</Muted> : null}
      </Card>
      <Card>
        <H2>Sync status</H2>
        <P>Connection: {status === 'online' ? '● Online' : status === 'syncing' ? '⟳ Syncing' : '○ Offline'}</P>
        <P>Pending actions: {queue.length}</P>
        {queue.map((a) => (
          <View key={a.action_id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderColor: '#E5E7EB' }}>
            <Text style={{ fontSize: 16, color: C.text }}>⏳ {a.label}</Text>
            <Muted>Pending · queued {a.queued_at}</Muted>
          </View>
        ))}
        <Btn title="Sync now" onPress={syncNow} disabled={!queue.length || status !== 'online'} />
        {queue.length && status !== 'online' ? <Muted>Will sync automatically when the connection returns.</Muted> : null}
      </Card>
      {results.length ? (
        <Card>
          <H2>Last sync results</H2>
          {results.map((r) => (
            <View key={r.action_id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderColor: '#E5E7EB' }}>
              <Badge status={r.status} />
              <Text style={{ fontSize: 16, color: C.text, marginTop: 4 }}>{r.label}</Text>
              <Muted>{r.message}</Muted>
            </View>
          ))}
        </Card>
      ) : null}
      <Card>
        <H2>Server</H2>
        <Field label="Server address" value={srv} onChangeText={setSrv} autoCapitalize="none" keyboardType="url" />
        <Notice kind="ok" text={saved} />
        <Btn title="Save server address" kind="secondary" onPress={async () => { await setServer(srv); setSaved('Server address saved.'); }} />
      </Card>
      <Btn title="Sign out" kind="danger" onPress={() => Alert.alert('Sign out?', queue.length ? 'You have pending actions; they stay on this phone.' : '',
        [{ text: 'Cancel', style: 'cancel' }, { text: 'Sign out', style: 'destructive', onPress: logout }])} />
    </ScrollView>
  );
}
