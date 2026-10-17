import React, { useEffect, useRef } from 'react';
import { Animated, Easing, Image, StyleSheet, Text } from 'react-native';
import { C } from './theme';

// Branded launch screen: logo scales in, title rises, then the screen fades into the app.
export default function Splash({ onDone }) {
  const logo = useRef(new Animated.Value(0)).current;
  const text = useRef(new Animated.Value(0)).current;
  const out = useRef(new Animated.Value(1)).current;
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    const anim = Animated.sequence([
      Animated.timing(logo, { toValue: 1, duration: 700, easing: Easing.out(Easing.back(1.4)), useNativeDriver: true }),
      Animated.timing(text, { toValue: 1, duration: 500, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.delay(1400),
      Animated.timing(out, { toValue: 0, duration: 400, useNativeDriver: true }),
    ]);
    anim.start(({ finished }) => { if (finished && done.current) done.current(); });
    return () => anim.stop();
  }, []); // run once

  return (
    <Animated.View style={[st.root, { opacity: out }]} accessible accessibilityLabel="NaSCon League, loading">
      <Animated.Image source={require('../assets/logo.png')} resizeMode="contain"
        style={[st.logo, { opacity: logo, transform: [{ scale: logo.interpolate({ inputRange: [0, 1], outputRange: [0.7, 1] }) }] }]} />
      <Animated.View style={{ alignItems: 'center', opacity: text,
        transform: [{ translateY: text.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) }] }}>
        <Text style={st.title}>NaSCon<Text style={{ color: C.accent }}> League</Text></Text>
        <Text style={st.tag}>Fixtures · Standings · Clubs · Store</Text>
      </Animated.View>
      <Text style={st.foot}>Multi-sport league platform</Text>
    </Animated.View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, width: '100%', height: '100%', backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' },
  logo: { width: 140, height: 140, borderRadius: 70, borderWidth: 1.5, borderColor: C.line, marginBottom: 28 },
  title: { fontSize: 30, fontWeight: '800', color: C.text, letterSpacing: -0.5 },
  tag: { marginTop: 10, fontSize: 14, color: C.muted, letterSpacing: 0.6 },
  foot: { position: 'absolute', bottom: 40, fontSize: 12, color: C.muted, letterSpacing: 1.4, textTransform: 'uppercase' },
});
