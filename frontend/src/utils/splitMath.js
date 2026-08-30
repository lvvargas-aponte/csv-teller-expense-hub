// The arithmetic behind every split editor: percent ↔ the two dollar figures.
//
// Extracted from SplitAdjustRow so the Shared page can offer the same editor
// without forking it. SplitAdjustRow is a <tr> built for the transactions
// table; the Shared page's rows are divs, so the markup cannot be shared even
// though the maths must be.

export const round2 = (n) => Math.round(n * 100) / 100;

export const parseDollars = (s) => {
  const n = parseFloat(String(s).replace(/[^0-9.-]/g, ''));
  return isNaN(n) ? 0 : n;
};

export const parsePercent = (s) => {
  const n = parseFloat(String(s).replace(/[^0-9.]/g, ''));
  if (isNaN(n)) return null;
  return Math.max(0, Math.min(100, n));
};

// Splits are absolute, not proportional — the two figures must sum to the
// transaction's own amount, which is why every helper here derives the second
// side from the first rather than storing a ratio.
export const shareOf = (total, percent) => round2((total * percent) / 100);

export const remainderOf = (total, share) => round2(total - share);

export const percentOf = (total, share) =>
  total > 0 ? round2((share / total) * 100) : 0;
