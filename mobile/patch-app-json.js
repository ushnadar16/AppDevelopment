// Run once after copying these files: `node patch-app-json.js`
// Allows rotation, sets the Android package, and allows http:// to the laptop backend in the APK.
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync('app.json', 'utf8'));
const e = cfg.expo;
e.name = 'NaSCon League';
e.orientation = 'default';
e.android = { ...(e.android || {}), package: 'com.nascon.league' };
e.plugins = (e.plugins || []).filter((p) => (Array.isArray(p) ? p[0] : p) !== 'expo-build-properties');
e.plugins.push(['expo-build-properties', { android: { usesCleartextTraffic: true } }]);
fs.writeFileSync('app.json', JSON.stringify(cfg, null, 2));
console.log('app.json updated');
