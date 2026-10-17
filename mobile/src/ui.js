import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useApp } from './AppContext';

export const C = {
  bg: '#F4F6FA', card: '#FFFFFF', text: '#111827', muted: '#4B5563', border: '#D1D5DB',
  ok: '#047857', warn: '#B45309', bad: '#B91C1C', info: '#1D4ED8',
};

export function Card({ children, style }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function H1({ children }) { return <Text style={s.h1} accessibilityRole="header">{children}</Text>; }
export function H2({ children }) { return <Text style={s.h2} accessibilityRole="header">{children}</Text>; }
export function P({ children, style }) { return <Text style={[s.p, style]}>{children}</Text>; }
export function Muted({ children, style }) { return <Text style={[s.muted, style]}>{children}</Text>; }

export function Btn({ title, onPress, kind = 'primary', disabled, small, accessibilityHint, style }) {
  const { theme } = useApp();
  const bg = kind === 'primary' ? theme.primary : kind === 'danger' ? C.bad : '#FFFFFF';
  const fg = kind === 'secondary' ? theme.primary : '#FFFFFF';
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={title}
      accessibilityHint={accessibilityHint} accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: bg, borderColor: theme.primary,
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1 }, style]}>
      <Text style={[s.btnText, { color: fg }]}>{title}</Text>
    </Pressable>
  );
}

export function Chip({ label, selected, onPress }) {
  const { theme } = useApp();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!selected }}
      accessibilityLabel={label}
      style={[s.chip, { borderColor: theme.primary, backgroundColor: selected ? theme.primary : '#FFFFFF' }]}>
      <Text style={{ color: selected ? '#FFFFFF' : theme.primary, fontWeight: '600', fontSize: 15 }}>
        {selected ? '✓ ' : ''}{label}
      </Text>
    </Pressable>
  );
}

export function Field({ label, ...props }) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor="#6B7280" style={s.input} {...props} />
    </View>
  );
}

export function Loading({ text = 'Loading…' }) {
  return (
    <View style={s.center} accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" />
      <Muted style={{ marginTop: 8 }}>{text}</Muted>
    </View>
  );
}

export function Empty({ text }) {
  return <View style={s.center}><Muted style={{ textAlign: 'center' }}>{text}</Muted></View>;
}

export function Notice({ kind = 'info', text }) {
  if (!text) return null;
  const color = { info: C.info, ok: C.ok, warn: C.warn, bad: C.bad }[kind];
  const icon = { info: 'ℹ', ok: '✓', warn: '⚠', bad: '✕' }[kind];
  return (
    <View style={[s.notice, { borderColor: color }]} accessibilityLiveRegion="polite">
      <Text style={{ color, fontSize: 15, fontWeight: '600' }}>{icon} {text}</Text>
    </View>
  );
}

const STATUS = {
  upcoming: ['Upcoming', C.info], in_progress: ['● Live', C.bad], completed: ['Full time', C.muted],
  clinched: ['✓ Qualified', C.ok], eliminated: ['✕ Out', C.bad], still_possible: ['In contention', C.warn],
  applied: ['✓ Saved', C.ok], rejected: ['✕ Rejected', C.bad], duplicate: ['= Duplicate', C.muted],
};
export function Badge({ status }) {
  const [label, color] = STATUS[status] || [status, C.muted];
  return (
    <View style={[s.badge, { borderColor: color }]}>
      <Text style={{ color, fontWeight: '700', fontSize: 13 }}>{label}</Text>
    </View>
  );
}

export function SyncBar({ onPress }) {
  const { status, queue } = useApp();
  const cfg = {
    online: ['● Online', C.ok],
    offline: ['○ Offline — showing saved data', C.bad],
    syncing: ['⟳ Syncing…', C.info],
  }[status];
  return (
    <Pressable onPress={onPress} accessibilityRole="button"
      accessibilityLabel={`${cfg[0]}. ${queue.length} pending actions. Open sync status.`}
      style={[s.sync, { backgroundColor: cfg[1] }]}>
      <Text style={s.syncText}>{cfg[0]}</Text>
      <Text style={s.syncText}>{queue.length ? `${queue.length} pending ›` : 'All synced ›'}</Text>
    </Pressable>
  );
}

export const money = (minor) => `PKR ${(minor / 100).toFixed(2)}`;

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, paddingBottom: 40 },
  card: { backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#E5E7EB' },
  h1: { fontSize: 24, fontWeight: '800', color: C.text, marginBottom: 8 },
  h2: { fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 8 },
  p: { fontSize: 16, color: C.text, lineHeight: 22 },
  muted: { fontSize: 14, color: C.muted, lineHeight: 20 },
  label: { fontSize: 15, fontWeight: '600', color: C.text, marginBottom: 6 },
  input: { minHeight: 48, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, fontSize: 16, backgroundColor: '#FFFFFF', color: C.text },
  btn: { minHeight: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, borderWidth: 2, marginVertical: 4 },
  btnSmall: { minHeight: 48, paddingHorizontal: 12 },
  btnText: { fontSize: 16, fontWeight: '700' },
  chip: { minHeight: 48, borderWidth: 2, borderRadius: 24, paddingHorizontal: 16, justifyContent: 'center', marginRight: 8, marginBottom: 8 },
  center: { padding: 32, alignItems: 'center', justifyContent: 'center' },
  notice: { borderLeftWidth: 4, backgroundColor: '#FFFFFF', padding: 12, borderRadius: 8, marginBottom: 12 },
  badge: { borderWidth: 1.5, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  sync: { minHeight: 44, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16 },
  syncText: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
  row: { flexDirection: 'row', alignItems: 'center' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
});
