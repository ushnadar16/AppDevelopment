// Brand palette: emerald green + ivory, with black used only for fine outlines.
export const EMERALD = '#2E5B47';
export const IVORY = '#F3EBD8';
export const BLACK = '#111111';
export const ACCENT = EMERALD;     // kept for older imports

export const C = {
  bg: IVORY,                 // app background
  card: '#FBF7EE',           // lighter ivory for cards
  raised: '#FFFDF8',         // inputs, unselected chips
  line: BLACK,               // thin black outlines
  softLine: 'rgba(17,17,17,0.18)', // dividers inside cards
  text: '#16231C',           // deep green-black text
  muted: '#55635B',
  accent: EMERALD,
  onAccent: IVORY,
  highlight: EMERALD,
  // status colours: always paired with an icon or word, never colour alone
  ok: EMERALD,
  warn: '#8A5A00',
  bad: '#B3261E',
  info: '#1F4E79',
};
