export const blankRow = () => ({
  _id: crypto.randomUUID(), accountId: null, name: '', balance: '', apr: '', min_payment: '',
});

export function aprBadgeClass(apr) {
  const v = parseFloat(apr) || 0;
  if (v >= 25) return 'ov-apr-badge--high';
  if (v >= 20) return 'ov-apr-badge--med';
  return 'ov-apr-badge--low';
}

export function fmtMonths(n) {
  if (!n || n <= 0) return '—';
  if (n < 12) return `${n} mo`;
  const yrs = Math.floor(n / 12);
  const mos = n % 12;
  return mos > 0 ? `${yrs}y ${mos}mo` : `${yrs}y`;
}

// Sort rows by the active payoff strategy.
//   Avalanche: rows with apr > 0 sorted by APR desc; rows without an APR append.
//   Snowball:  rows with balance > 0 sorted by balance asc; rows with zero balance append.
// "Active" depends on the strategy because each one needs a different non-zero key.
export function sortByStrategy(rows, strategy) {
  const hasKey = strategy === 'avalanche'
    ? (r) => (parseFloat(r.apr)     || 0) > 0
    : (r) => (parseFloat(r.balance) || 0) > 0;
  const active   = rows.filter(hasKey);
  const inactive = rows.filter((r) => !hasKey(r));
  const sorted = [...active].sort((a, b) =>
    strategy === 'avalanche'
      ? (parseFloat(b.apr)     || 0) - (parseFloat(a.apr)     || 0)
      : (parseFloat(a.balance) || 0) - (parseFloat(b.balance) || 0)
  );
  return [...sorted, ...inactive];
}
