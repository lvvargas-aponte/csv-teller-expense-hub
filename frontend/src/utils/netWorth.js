/**
 * Net worth, told as four parts instead of one number.
 *
 * A house entering the total moves it by six figures without making a hard
 * month any easier, so two things have to be said wherever the total is: which
 * part moved, and how much of the total could actually be reached. Both the
 * dashboard KPI and the Net Worth card say them, from here.
 */
const WHOLE_DOLLARS = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
});

// Property is listed apart from investments because it is not tradeable, and
// debt is shown rather than netted away silently.
export function netWorthComposition(summary) {
  if (!summary) return null;
  return [
    { key: 'cash', label: 'Cash', value: summary.total_cash ?? 0 },
    { key: 'investments', label: 'Investments', value: summary.total_investments ?? 0 },
    { key: 'property', label: 'Property', value: summary.total_real_assets ?? 0 },
    { key: 'debt', label: 'Debt', value: -(summary.total_credit_debt ?? 0) },
  ];
}

// "$138,000 liquid" — the total less the property and vehicles inside it, or
// null when the household owns none and the distinction would be noise.
export function liquidLabel(summary, fallbackTotal = null) {
  const realAssets = summary?.total_real_assets ?? 0;
  const total = summary?.net_worth ?? fallbackTotal;
  if (realAssets <= 0 || total === null || total === undefined) return null;
  return `${WHOLE_DOLLARS.format(total - realAssets)} liquid`;
}
