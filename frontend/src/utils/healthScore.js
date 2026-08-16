/**
 * Financial health score, 0-100.
 *
 * Extracted from FinancesPage so the sidebar, dashboard banner, and future
 * screens all read one implementation.
 *
 * Weighted: net-worth direction 30%, credit utilization 30%, spending trend
 * 40%. Signals with no data are skipped and the remaining weights are
 * renormalized, so a household with no credit cards isn't penalized for it.
 * Returns null when nothing is known — the UI shows "—" rather than a zero
 * that reads like a failing grade.
 */
export function computeHealthScore({ netWorth, trend, creditHealth, monthlyTotals }) {
  let score = 0;
  let weight = 0;

  // Net worth direction (30%)
  const nw = trend?.current_net_worth ?? netWorth;
  if (nw !== null && nw !== undefined) {
    if (trend?.delta_30d !== null && trend?.delta_30d !== undefined) {
      const base = Math.abs(nw) || 1;
      const ratio = trend.delta_30d / base;
      const sub = Math.max(0, Math.min(1, 0.5 + ratio * 5));
      score += sub * 30; weight += 30;
    } else {
      // A position but no trend — neutral, leaning on the sign.
      const sub = nw >= 0 ? 0.6 : 0.4;
      score += sub * 30; weight += 30;
    }
  }

  // Credit utilization (30%) — only when there are cards to utilize.
  if (creditHealth?.accounts?.length > 0) {
    const u = creditHealth.overall_utilization_pct ?? 0;
    const sub = Math.max(0, 1 - u / 100);
    score += sub * 30; weight += 30;
  }

  // Spending trend (40%) — a proxy for savings rate when income is unknown.
  if (monthlyTotals && monthlyTotals.length >= 2) {
    const last = monthlyTotals[monthlyTotals.length - 1].total || 0;
    const prev = monthlyTotals[monthlyTotals.length - 2].total || 0;
    if (prev > 0) {
      const change = (last - prev) / prev;
      const sub = Math.max(0, Math.min(1, 0.5 - change));
      score += sub * 40; weight += 40;
    }
  }

  if (weight === 0) return null;
  return Math.round((score / weight) * 100);
}
