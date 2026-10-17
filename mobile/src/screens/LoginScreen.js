import React, { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { useApp } from '../AppContext';
import { Btn, C, Card, Chip, Field, H1, Muted, Notice, s } from '../ui';
import { errorText } from '../messages';

const DEMO = [['Organizer', 'organizer@nascon.test'], ['Club Manager', 'manager@nascon.test'],
  ['Player', 'player@nascon.test'], ['Viewer', 'viewer@nascon.test'], ['Super-Admin', 'admin@nascon.test']];

export default function LoginScreen() {
  const { login, server, setServer, status } = useApp();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [srv, setSrv] = useState(server);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!email.trim() || !password) { setError('Please enter your email and password.'); return; }
    setBusy(true); setError('');
    try {
      if (srv.trim() !== server) await setServer(srv);
      await login(email.trim().toLowerCase(), password);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <KeyboardAvoidingView style={s.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={s.pad} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: 'center', marginTop: 24, marginBottom: 28 }}>
          <Image source={require('../../assets/logo.png')} style={{ width: 92, height: 92, borderRadius: 46, borderWidth: 1.5, borderColor: C.line, marginBottom: 16 }}
            accessibilityLabel="NaSCon League logo" />
          <Text style={{ fontSize: 26, fontWeight: '800', color: C.text, letterSpacing: -0.4 }}>NaSCon<Text style={{ color: C.accent }}> League</Text></Text>
          <Muted style={{ marginTop: 6 }}>Sign in to manage your league and club</Muted>
        </View>
        <Card>
          <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none"
            keyboardType="email-address" placeholder="you@club.com" autoComplete="email" />
          <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry placeholder="Password" />
          <Notice kind="bad" text={error} />
          <Btn title={busy ? 'Signing in…' : 'Sign in'} onPress={submit} disabled={busy} />
        </Card>
        <Card>
          <Muted style={{ marginBottom: 8 }}>Demo accounts (password Nascon@26) — tap to fill:</Muted>
          <View style={s.wrap}>
            {DEMO.map(([label, mail]) => (
              <Chip key={mail} label={label} selected={email === mail}
                onPress={() => { setEmail(mail); setPassword('Nascon@26'); }} />
            ))}
          </View>
        </Card>
        <Card>
          <Field label="Server address" value={srv} onChangeText={setSrv} autoCapitalize="none"
            keyboardType="url" placeholder="http://192.168.43.15:8080" />
          <Muted>Server is {status === 'offline' ? 'not reachable' : 'reachable'}. Phone: use your laptop's IP. Emulator: http://10.0.2.2:8080</Muted>
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
