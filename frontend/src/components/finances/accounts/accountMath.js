import { daysUntilNextDue } from './dueDate';

const num = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
};

// Merge a balances-summary account with its user-supplied details into the
// shape the row / summary bar render from.
//
// Available credit normally comes from the bank. For manual accounts there is
// no bank to ask, so a user-entered credit limit derives it — editing the limit
// on a manual card updates its available credit and, through it, the summary
// bar. Synced cards keep the provider's number so an edited limit can never
// silently contradict the bank.
export function buildCreditRow(account, details = {}) {
  const owed = num(account.ledger) ?? 0;
  const limit = num(details.credit_limit);
  const reported = num(account.available);
  const derived = limit === null ? null : Math.max(0, limit - owed);
  const available = account.manual ? (derived ?? reported ?? 0) : (reported ?? derived ?? 0);

  return {
    account,
    id: account.id,
    name: account.name,
    institution: account.institution,
    manual: !!account.manual,
    owed,
    limit,
    available,
    apr: num(details.apr),
    minPayment: num(details.minimum_payment),
    statementDay: num(details.statement_day),
    dueDay: num(details.due_day),
    openedOn: details.opened_on ?? null,
    utilPct: limit && limit > 0 ? (owed / limit) * 100 : null,
    dueInDays: daysUntilNextDue(details.due_day),
    // The "starting" figure a manual account's edit is stored against — not
    // the live computed owed/available above, which already has linked-txn
    // delta folded in. Seeding the balance editor from the computed value
    // instead of this would make every unchanged save walk the balance by
    // the delta again. See PUT /api/balances/{id} and balances_service.py.
    startingBalance: num(account.starting_balance),
    linkedTxnCount: account.linked_txn_count ?? 0,
    linkedLastDate: account.linked_last_date ?? null,
  };
}

export function buildCashRow(account) {
  const available = num(account.available) ?? 0;
  const ledger = num(account.ledger) ?? 0;
  return {
    account,
    id: account.id,
    name: account.name,
    institution: account.institution,
    manual: !!account.manual,
    available,
    ledger,
    showLedger: Math.abs(available - ledger) > 0.005,
    startingBalance: num(account.starting_balance),
    linkedTxnCount: account.linked_txn_count ?? 0,
    linkedLastDate: account.linked_last_date ?? null,
  };
}

const ASSET_SUBTYPE_LABELS = { home: 'Home', vehicle: 'Vehicle' };

// A home or vehicle: the stored figure is the whole story. There is no ledger
// to reconcile against and no transaction that moves it — only a user edit.
export function buildAssetRow(account) {
  const subtype = (account.subtype || '').toLowerCase();
  return {
    account,
    id: account.id,
    name: account.name,
    subtype,
    subtypeLabel: ASSET_SUBTYPE_LABELS[subtype] || (account.subtype || 'Other'),
    value: num(account.available) ?? num(account.ledger) ?? 0,
    valuationUpdatedOn: account.valuation_updated_on ?? null,
    // Both come from the summary, which joins the asset to its loan. null is
    // "unknown" — an unlinked asset, or a link whose loan is gone.
    securedByAccountId: account.secured_by_account_id ?? null,
    securedDebt: num(account.secured_debt),
    equity: num(account.equity),
  };
}

// What a brokerage or retirement account is worth. `ledger` is the position
// value; `available` is the cash that happens to be settled and uninvested,
// which is 0 for a fully-invested account. Ledger-first, so a row and the
// section total that sums it can never disagree.
export function investmentValue(account) {
  return num(account.ledger) ?? num(account.available) ?? 0;
}

// Per-section totals shown on each group header. Net worth, utilization and
// the next payment deliberately live on the Overview and Dashboard pages
// instead — this page lists accounts, it doesn't summarize the household.
export function summarize(creditRows, cashRows, investmentRows = [], assetRows = []) {
  return {
    totalOwed: creditRows.reduce((s, r) => s + r.owed, 0),
    totalCash: cashRows.reduce((s, r) => s + r.available, 0),
    totalInvestments: investmentRows.reduce((s, a) => s + investmentValue(a), 0),
    totalAssets: assetRows.reduce((s, r) => s + r.value, 0),
  };
}
