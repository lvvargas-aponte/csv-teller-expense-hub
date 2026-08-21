/**
 * Account bucketing — the single rule for "is this cash, credit, or an
 * investment?" on the frontend.
 *
 * This mirrors the backend's ``analytics._classify_account_bucket``, which is
 * what ``summary.total_cash`` / ``total_investments`` are summed with. Any view
 * that groups accounts must use these helpers, or its groups stop adding up to
 * the totals the same payload reports — which is exactly how a 401(k) filed as
 * a depository account ended up listed under both "Cash & Savings" and
 * "Investments" at the same time.
 *
 * If ``_INVESTMENT_SUBTYPES`` grows in analytics.py, mirror the new entries here.
 */

const INVESTMENT_SUBTYPES = new Set([
  '401k', '401(k)', '403b', '403(b)', 'ira', 'roth_ira', 'roth ira',
  'brokerage', 'hsa', 'investment', 'retirement', 'rollover_ira',
  'sep_ira', 'simple_ira', '529',
]);

/** An investment/retirement account — by type, or by a recognized subtype on a
 *  depository account (so a hand-entered 401(k) still counts as one). */
export const isInvestment = (a) =>
  (a?.type || '').toLowerCase() === 'investment' ||
  INVESTMENT_SUBTYPES.has((a?.subtype || '').toLowerCase().trim());

/** Spendable cash: depository, minus anything the rule above claims. */
export const isCash = (a) =>
  (a?.type || '').toLowerCase() === 'depository' && !isInvestment(a);

/** A liability. Investment subtypes can't apply here — a credit line is debt. */
export const isCredit = (a) => (a?.type || '').toLowerCase() === 'credit';

/** Split a summary's account list into the three groups, once. */
export function groupAccounts(accounts = []) {
  return {
    credit:      accounts.filter(isCredit),
    cash:        accounts.filter(isCash),
    investments: accounts.filter(isInvestment),
  };
}

export { INVESTMENT_SUBTYPES };
