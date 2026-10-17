import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { AppProvider, useApp } from './src/AppContext';
import { Loading, SyncBar } from './src/ui';
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

const ICONS = { Fixtures: 'calendar', Standings: 'podium', Store: 'cart', Club: 'shield', Roster: 'people', Score: 'add-circle', Account: 'person' };

function Tabs() {
  const { session, theme } = useApp();
  const role = session.user.role;
  return (
    <Tab.Navigator screenOptions={({ route }) => ({
      tabBarActiveTintColor: theme.primary, tabBarInactiveTintColor: '#4B5563',
      tabBarLabelStyle: { fontSize: 12, fontWeight: '600' }, tabBarStyle: { minHeight: 60, paddingBottom: 6 },
      headerStyle: { backgroundColor: theme.primary }, headerTintColor: '#FFFFFF', headerStatusBarHeight: 0,
      tabBarIcon: ({ color, size }) => <Ionicons name={ICONS[route.name]} color={color} size={size} />,
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
  const { ready, session, theme } = useApp();
  if (!ready) return <Loading text="Starting…" />;
  const header = { headerStyle: { backgroundColor: theme.primary }, headerTintColor: '#FFFFFF', headerTopInsetEnabled: false };
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.primary }} edges={['top']}>
      <SyncBar onPress={() => session && nav.isReady() && nav.navigate('Tabs', { screen: 'Account' })} />
      <NavigationContainer ref={nav}>
        <Stack.Navigator screenOptions={header}>
          {!session ? (
            <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'NaSCon League' }} />
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
        <StatusBar style="light" />
        <Root />
      </AppProvider>
    </SafeAreaProvider>
  );
}
