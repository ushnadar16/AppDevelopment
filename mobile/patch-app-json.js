// Run once after copying these files: `node patch-app-json.js`
// Allows rotation, sets the Android package, and allows http:// to the laptop backend in the APK.
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync('app.json', 'utf8'));
const e = cfg.expo;
e.name = 'NaSCon League';
e.orientation = 'default';
e.userInterfaceStyle = 'light';
e.icon = './assets/icon.png';
e.backgroundColor = '#F3EBD8';
e.splash = { ...(e.splash || {}), image: './assets/splash-icon.png', backgroundColor: '#F3EBD8', resizeMode: 'contain' };
e.android = { ...(e.android || {}), adaptiveIcon: { ...((e.android || {}).adaptiveIcon || {}), foregroundImage: './assets/android-icon-foreground.png', backgroundColor: '#0B4B3B' } };
e.plugins = (e.plugins || []).map((p) => {
  const name = Array.isArray(p) ? p[0] : p;
  if (name !== 'expo-splash-screen') return p;
  const opts = Array.isArray(p) ? p[1] || {} : {};
  return ['expo-splash-screen', { ...opts, image: './assets/splash-icon.png', imageWidth: 160, backgroundColor: '#F3EBD8' }];
});
e.android = { ...(e.android || {}), package: 'com.nascon.league' };
e.plugins = (e.plugins || []).filter((p) => (Array.isArray(p) ? p[0] : p) !== 'expo-build-properties');
e.plugins.push(['expo-build-properties', { android: { usesCleartextTraffic: true } }]);
fs.writeFileSync('app.json', JSON.stringify(cfg, null, 2));
console.log('app.json updated');
