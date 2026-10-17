import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useApp } from './AppContext';
import { C } from './theme';

export { C };

export function Card({ children, style }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function H1({ children, style }) { return <Text style={[s.h1, style]} accessibilityRole="header">{children}</Text>; }
export function H2({ children, style }) { return <Text style={[s.h2, style]} accessibilityRole="header">{children}</Text>; }
export function P({ children, style }) { return <Text style={[s.p, style]}>{children}</Text>; }
export function Muted({ children, style }) { return <Text style={[s.muted, style]}>{children}</Text>; }
export function Eyebrow({ children, style }) { return <Text style={[s.eyebrow, style]}>{children}</Text>; }

export function Btn({ title, onPress, kind = 'primary', disabled, small, accessibilityHint, style }) {
  const look = {
    primary: { bg: C.accent, fg: C.onAccent, border: C.line },
    secondary: { bg: 'transparent', fg: C.accent, border: C.accent },
    danger: { bg: 'transparent', fg: C.bad, border: C.bad },
  }[kind];
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={title}
      accessibilityHint={accessibilityHint} accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: look.bg, borderColor: look.border,
        opacity: disabled ? 0.4 : pressed ? 0.75 : 1 }, style]}>
      <Text style={[s.btnText, { color: look.fg }]}>{title}</Text>
    </Pressable>
  );
}

export function Chip({ label, selected, onPress }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!selected }}
      accessibilityLabel={label}
      style={({ pressed }) => [s.chip, selected ? s.chipOn : s.chipOff, pressed && { opacity: 0.8 }]}>
      <Text style={{ color: selected ? C.onAccent : C.text, fontWeight: '600', fontSize: 15 }}>
        {selected ? '✓ ' : ''}{label}
      </Text>
    </Pressable>
  );
}

export function Field({ label, ...props }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor="#7C877F" selectionColor={C.ok}
        style={s.input} {...props} />
    </View>
  );
}

export function Loading({ text = 'Loading…' }) {
  return (
    <View style={[s.center, { flex: 1, backgroundColor: C.bg }]} accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" color={C.highlight} />
      <Muted style={{ marginTop: 10 }}>{text}</Muted>
    </View>
  );
}

export function Empty({ text }) {
  return (
    <View style={s.center}>
      <Text style={{ fontSize: 28, color: C.muted, marginBottom: 8 }}>◌</Text>
      <Muted style={{ textAlign: 'center' }}>{text}</Muted>
    </View>
  );
}

export function Notice({ kind = 'info', text }) {
  if (!text) return null;
  const color = { info: C.info, ok: C.ok, warn: C.warn, bad: C.bad }[kind];
  const icon = { info: 'ℹ', ok: '✓', warn: '⚠', bad: '✕' }[kind];
  return (
    <View style={[s.notice, { borderLeftColor: color }]} accessibilityLiveRegion="polite">
      <Text style={{ color: C.text, fontSize: 15, lineHeight: 21 }}>
        <Text style={{ color, fontWeight: '800' }}>{icon}  </Text>{text}
      </Text>
    </View>
  );
}

const STATUS = {
  upcoming: ['Upcoming', C.info], in_progress: ['● LIVE', C.bad], completed: ['Full time', C.muted],
  clinched: ['✓ Qualified', C.ok], eliminated: ['✕ Out', C.bad], still_possible: ['In contention', C.warn],
  applied: ['✓ Saved', C.ok], rejected: ['✕ Rejected', C.bad], duplicate: ['= Duplicate', C.muted],
};
export function Badge({ status }) {
  const [label, color] = STATUS[status] || [status, C.muted];
  return (
    <View style={[s.badge, { borderColor: color }]}>
      <Text style={{ color, fontWeight: '800', fontSize: 12, letterSpacing: 0.6 }}>{label}</Text>
    </View>
  );
}

export function SyncBar({ onPress }) {
  const { status, queue } = useApp();
  const cfg = {
    online: ['Online', C.ok],
    offline: ['Offline · showing saved data', C.bad],
    syncing: ['Syncing…', C.info],
  }[status];
  return (
    <Pressable onPress={onPress} accessibilityRole="button"
      accessibilityLabel={`${cfg[0]}. ${queue.length} pending actions. Open sync status.`} style={s.sync}>
      <View style={s.row}>
        <View style={[s.dot, { backgroundColor: cfg[1] }]} />
        <Text style={[s.syncText, { color: cfg[1] }]}>{cfg[0]}</Text>
      </View>
      <Text style={s.syncMeta}>{queue.length ? `${queue.length} pending ›` : 'All synced ›'}</Text>
    </Pressable>
  );
}

const TEAM_NAMES = {
  'club-alpha-1': 'Alpha Falcons', 'club-alpha-2': 'Alpha Lions', 'demo-alpha-3': 'Alpha Rangers',
  'demo-alpha-4': 'Alpha City', 'club-beta-1': 'Beta Stars',
};
export const teamName = (id) => TEAM_NAMES[id] || String(id || '').replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export const money = (minor) => `PKR ${(minor / 100).toFixed(2)}`;

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, paddingBottom: 48 },
  card: { backgroundColor: C.card, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: StyleSheet.hairlineWidth * 2, borderColor: C.line },
  h1: { fontSize: 24, fontWeight: '800', color: C.text, marginBottom: 6, letterSpacing: -0.3 },
  h2: { fontSize: 17, fontWeight: '700', color: C.text, marginBottom: 10 },
  p: { fontSize: 16, color: C.text, lineHeight: 23 },
  muted: { fontSize: 14, color: C.muted, lineHeight: 20 },
  eyebrow: { fontSize: 12, color: C.muted, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 6 },
  label: { fontSize: 14, fontWeight: '600', color: C.muted, marginBottom: 6 },
  input: { minHeight: 50, borderWidth: 1, borderColor: C.line, borderRadius: 12, paddingHorizontal: 14, fontSize: 16, backgroundColor: C.raised, color: C.text },
  btn: { minHeight: 50, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, borderWidth: 1.5, marginVertical: 5 },
  btnSmall: { minHeight: 48, paddingHorizontal: 14 },
  btnText: { fontSize: 16, fontWeight: '700', letterSpacing: 0.2 },
  chip: { minHeight: 48, borderWidth: 1, borderRadius: 24, paddingHorizontal: 16, justifyContent: 'center', marginRight: 8, marginBottom: 8 },
  chipOn: { backgroundColor: C.accent, borderColor: C.line },
  chipOff: { backgroundColor: C.raised, borderColor: C.softLine },
  center: { padding: 32, alignItems: 'center', justifyContent: 'center' },
  notice: { borderLeftWidth: 4, backgroundColor: C.card, padding: 14, borderRadius: 12, marginBottom: 12, borderWidth: StyleSheet.hairlineWidth * 2, borderColor: C.line },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start' },
  sync: { minHeight: 40, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16,
    backgroundColor: C.card, borderBottomWidth: StyleSheet.hairlineWidth * 2, borderColor: C.line },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  syncText: { fontWeight: '700', fontSize: 14 },
  syncMeta: { color: C.muted, fontWeight: '600', fontSize: 14 },
  row: { flexDirection: 'row', alignItems: 'center' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  divider: { borderBottomWidth: 1, borderColor: C.softLine },
});
