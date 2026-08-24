/**
 * One account classifier for the whole frontend — a port of backend
 * `analytics.classify_account_bucket`.
 *
 * Two screens used to answer differently: the Accounts tab grouped on `type`
 * alone while Overview carried its own subtype list, so a manual Roth IRA
 * showed as cash on one page and an investment on the other. Everything that
 * needs to know what an account *is* calls `classifyAccountBucket`.
 *
 * The subtype list exists in two languages, so it drifts. `loadInvestmentSubtypes`
 * pulls the authoritative list from the backend once per session; the bundled
 * constant below is the offline fallback.
 */
import { getAccountsMetadata } from '../api/accounts';

export const INVESTMENT_SUBTYPES = new Set([
  '401k', '401(k)', '403b', '403(b)', 'ira', 'roth_ira', 'roth ira',
  'brokerage', 'hsa', 'investment', 'retirement', 'rollover_ira',
  'sep_ira', 'simple_ira', '529',
]);

let serverSubtypes = null;

/** Install the server's subtype list (or `null` / `[]` to fall back). */
export function setInvestmentSubtypes(subtypes) {
  serverSubtypes = subtypes && subtypes.length
    ? new Set(subtypes.map((s) => String(s).toLowerCase().trim()))
    : null;
}

let pendingLoad = null;

/** Fetch the server's subtype list once per session; failures keep the fallback. */
export function loadInvestmentSubtypes() {
  if (!pendingLoad) {
    pendingLoad = getAccountsMetadata()
      .then((r) => setInvestmentSubtypes(r.data?.investment_subtypes))
      .catch(() => { /* offline or old backend — the bundled list stands */ });
  }
  return pendingLoad;
}

export function classifyAccountBucket(account) {
  const type = (account?.type || '').toLowerCase();
  const subtype = (account?.subtype || '').toLowerCase().trim();
  const subtypes = serverSubtypes || INVESTMENT_SUBTYPES;

  if (type === 'investment' || subtypes.has(subtype)) return 'investment';
  if (type === 'depository') return 'cash';
  if (type === 'credit') return 'credit';
  return 'other';
}
