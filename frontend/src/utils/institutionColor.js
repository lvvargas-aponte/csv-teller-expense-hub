// Stable per-institution chip colors. The design hardcodes Barclays/Discover/Chase
// hues; for any other bank we hash the name into a fixed 6-entry palette so the
// same institution always gets the same color across renders.

const PALETTE = [
  { dot: '#1d4ed8', border: '#bfdbfe', bg: '#eff6ff', color: '#1d4ed8' }, // blue
  { dot: '#dc2626', border: '#fecaca', bg: '#fef2f2', color: '#dc2626' }, // red
  { dot: '#0369a1', border: '#bae6fd', bg: '#f0f9ff', color: '#0369a1' }, // sky
  { dot: '#7c3aed', border: '#ddd6fe', bg: '#f5f3ff', color: '#7c3aed' }, // purple
  { dot: '#d97706', border: '#fed7aa', bg: '#fff7ed', color: '#d97706' }, // amber
  { dot: '#0d9488', border: '#99f6e4', bg: '#f0fdfa', color: '#0d9488' }, // teal
];

const KNOWN = {
  barclays: PALETTE[0],
  discover: PALETTE[1],
  chase:    PALETTE[2],
};

export function chipColorFor(name) {
  const key = (name || '').trim().toLowerCase();
  if (!key) return PALETTE[5];
  if (KNOWN[key]) return KNOWN[key];
  let h = 0;
  for (let i = 0; i < key.length; i++) {
    h = (h * 31 + key.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}
