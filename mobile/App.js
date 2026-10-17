import React, { useState } from 'react';
import { Image, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { DefaultTheme, NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { AppProvider, useApp } from './src/AppContext';
import { C } from './src/theme';
import { Loading, SyncBar } from './src/ui';
import Splash from './src/Splash';
import LoginScreen from './src/screens/LoginScreen';
import FixturesScreen from './src/screens/FixturesScreen';
import MatchScreen from './src/screens/MatchScreen';
import StandingsScreen from './src/screens/StandingsScreen';
import ClubScreen from './src/screens/ClubScreen';
import StoreScreen from './src/screens/StoreScreen';
import ReceiptScreen from './src/screens/ReceiptScreen';
import RosterScreen from './src/screens/RosterScreen';
import ScoringScreen from './src/screens/ScoringScreen';
import AccountScreen from './src/screens/AccountScreen';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();
const nav = createNavigationContainerRef();

const NAV_THEME = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, primary: C.accent, background: C.bg, card: C.card, text: C.text, border: C.line, notification: C.accent },
};

function BrandTitle({ children }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
      <Image source={require('./assets/logo-small.png')} accessibilityLabel="NaSCon League logo"
        style={{ width: 32, height: 32, borderRadius: 16, borderWidth: 1, borderColor: C.line, marginRight: 10 }} />
      <Text numberOfLines={1} style={{ fontWeight: '700', fontSize: 18, color: C.text, maxWidth: 240 }}>{children}</Text>
    </View>
  );
}

const HEADER = {
  headerStyle: { backgroundColor: C.card },
  headerTintColor: C.text,
  headerTitleAlign: 'left',
  headerTitle: (props) => <BrandTitle>{props.children}</BrandTitle>,
  headerShadowVisible: false,
};

const ICONS = {
  Fixtures: ['calendar', 'calendar-outline'], Standings: ['podium', 'podium-outline'], Store: ['bag-handle', 'bag-handle-outline'],
  Club: ['shield', 'shield-outline'], Roster: ['people', 'people-outline'], Score: ['add-circle', 'add-circle-outline'],
  Account: ['person-circle', 'person-circle-outline'],
};

function Tabs() {
  const { session } = useApp();
  const role = session.user.role;
  return (
    <Tab.Navigator screenOptions={({ route }) => ({
      ...HEADER,
      headerStatusBarHeight: 0,
      tabBarActiveTintColor: C.accent,
      tabBarInactiveTintColor: C.muted,
      tabBarLabelStyle: { fontSize: 11, fontWeight: '700' },
      tabBarStyle: { backgroundColor: C.card, borderTopColor: C.line, borderTopWidth: 1, minHeight: 62, paddingBottom: 6, paddingTop: 4 },
      tabBarIcon: ({ color, size, focused }) => <Ionicons name={ICONS[route.name][focused ? 0 : 1]} color={color} size={size} />,
      tabBarAccessibilityLabel: `${route.name} tab`,
    })}>
      <Tab.Screen name="Fixtures" component={FixturesScreen} />
      <Tab.Screen name="Standings" component={StandingsScreen} />
      <Tab.Screen name="Store" component={StoreScreen} />
      <Tab.Screen name="Club" component={ClubScreen} />
      {['club_manager', 'super_admin'].includes(role) ? <Tab.Screen name="Roster" component={RosterScreen} /> : null}
      {['league_organizer', 'super_admin'].includes(role) ? <Tab.Screen name="Score" component={ScoringScreen} options={{ title: 'Scoring' }} /> : null}
      <Tab.Screen name="Account" component={AccountScreen} />
    </Tab.Navigator>
  );
}

function Root() {
  const { ready, session } = useApp();
  const [splashDone, setSplashDone] = useState(false);
  // The splash owns the whole screen first; navigation only mounts after it finishes.
  if (!splashDone) return <Splash onDone={() => setSplashDone(true)} />;
  if (!ready) return <Loading text="Starting…" />;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.card }} edges={['top']}>
      <SyncBar onPress={() => session && nav.isReady() && nav.navigate('Tabs', { screen: 'Account' })} />
      <NavigationContainer ref={nav} theme={NAV_THEME}>
        <Stack.Navigator screenOptions={{ ...HEADER, headerTopInsetEnabled: false, contentStyle: { backgroundColor: C.bg } }}>
          {!session ? (
            <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
          ) : (
            <>
              <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
              <Stack.Screen name="Match" component={MatchScreen} options={({ route }) => ({ title: route.params.title || 'Match' })} />
              <Stack.Screen name="Receipt" component={ReceiptScreen} />
              <Stack.Screen name="Scoring" component={ScoringScreen} options={{ title: 'Record score' }} />
            </>
          )}
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <StatusBar style="dark" backgroundColor={C.card} />
        <Root />
      </AppProvider>
    </SafeAreaProvider>
  );
}
