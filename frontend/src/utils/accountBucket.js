/**
 * One account classifier for the whole frontend — a port of backend
 * `analytics.classify_account_bucket`.
 *
 * Two screens used to answer differently: the Accounts tab grouped on `type`
 * alone while Overview carried its own subtype list, so a manual Roth IRA
 * showed as cash on one page and an investment on the other. Everything that
 * needs to know what an account *is* calls `classifyAccountBucket`.
 *
 * The subtype lists exist in two languages, so they drift. `loadAccountVocabulary`
 * pulls the authoritative ones from the backend in a single call once per
 * session; the bundled constants below are the offline fallback.
 */
import { getAccountsMetadata } from '../api/accounts';

export const INVESTMENT_SUBTYPES = new Set([
  '401k', '401(k)', '403b', '403(b)', 'ira', 'roth_ira', 'roth ira',
  'brokerage', 'hsa', 'investment', 'retirement', 'rollover_ira',
  'sep_ira', 'simple_ira', '529',
]);

// Installment debt: a fixed principal on a fixed schedule, as opposed to a
// revolving line. It has no credit limit to be a percentage of, so the backend
// leaves it out of utilization — and avalanche/snowball ordering does not apply
// to it either, so the payoff planner leaves it out too.
export const INSTALLMENT_SUBTYPES = new Set([
  'loan', 'mortgage', 'student', 'auto',
]);

let serverSubtypes = null;
let serverInstallment = null;

const asSet = (list) => (list && list.length
  ? new Set(list.map((s) => String(s).toLowerCase().trim()))
  : null);

/** Install the server's investment subtypes (or `null` / `[]` to fall back). */
export function setInvestmentSubtypes(subtypes) {
  serverSubtypes = asSet(subtypes);
}

/** Install the server's installment subtypes (or `null` / `[]` to fall back). */
export function setInstallmentSubtypes(subtypes) {
  serverInstallment = asSet(subtypes);
}

let pendingLoad = null;

/**
 * Fetch both subtype lists once per session; failures keep the bundled ones.
 * One request covers both — /accounts/metadata returns them together.
 */
export function loadAccountVocabulary() {
  if (!pendingLoad) {
    pendingLoad = getAccountsMetadata()
      .then((r) => {
        setInvestmentSubtypes(r.data?.investment_subtypes);
        setInstallmentSubtypes(r.data?.installment_subtypes);
      })
      .catch(() => { /* offline or old backend — the bundled lists stand */ });
  }
  return pendingLoad;
}

export function classifyAccountBucket(account) {
  const type = (account?.type || '').toLowerCase();
  const subtype = (account?.subtype || '').toLowerCase().trim();
  const subtypes = serverSubtypes || INVESTMENT_SUBTYPES;

  // Real assets first: 'investment' is a legal subtype string, and a house
  // labelled that way is still a house, not a tradeable holding.
  if (type === 'asset') return 'real_asset';
  if (type === 'investment' || subtypes.has(subtype)) return 'investment';
  if (type === 'depository') return 'cash';
  if (type === 'credit') return 'credit';
  return 'other';
}

// A credit account that is a loan rather than a card. Mirrors
// `analytics.is_installment`; the subtype list comes from the same endpoint.
export function isInstallmentLoan(account) {
  if (classifyAccountBucket(account) !== 'credit') return false;
  const subtype = (account?.subtype || '').toLowerCase().trim();
  return (serverInstallment || INSTALLMENT_SUBTYPES).has(subtype);
}
