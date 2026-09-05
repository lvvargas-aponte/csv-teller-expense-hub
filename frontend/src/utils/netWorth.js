/**
 * Net worth, told as four parts instead of one number.
 *
 * A house entering the total moves it by six figures without making a hard
 * month any easier, so two things have to be said wherever the total is: which
 * part moved, and how much of the total could actually be reached. Both the
 * dashboard KPI and the Net Worth card say them, from here.
 */
import { classifyAccountBucket, isInstallmentLoan } from './accountBucket';

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

// The same four parts, sized for a to-scale bar and with the debt split.
//
// `total_credit_debt` is one figure, and on a household with a mortgage it is
// overwhelmingly one account: showing it whole says "you owe $430,002" and
// leaves the reader to guess what that is. Split, it says the mortgage is 97%
// of it — which is the fact that decides whether a negative net worth is
// alarming or ordinary.
export function balanceSheetParts(summary) {
  if (!summary) return null;

  let revolving = 0;
  let installment = 0;
  for (const account of summary.accounts || []) {
    if (classifyAccountBucket(account) !== 'credit') continue;
    if (account.closed_on) continue;
    const owed = Math.abs(account.ledger ?? 0);
    if (isInstallmentLoan(account)) {
      installment += owed;
    } else {
      revolving += owed;
    }
  }

  const segments = [
    { key: 'cash', label: 'Cash', value: summary.total_cash ?? 0, fill: 'var(--good)' },
    { key: 'investments', label: 'Investments', value: summary.total_investments ?? 0, fill: 'var(--accent)' },
    { key: 'property', label: 'Property', value: summary.total_real_assets ?? 0, fill: 'var(--purple)' },
    { key: 'revolving', label: 'Cards', value: revolving, fill: 'var(--amber)' },
    { key: 'installment', label: 'Loans', value: installment, fill: 'var(--red)' },
  ].filter((s) => s.value > 0);

  const gross = segments.reduce((sum, s) => sum + s.value, 0);
  const total = summary.net_worth ?? 0;

  return {
    segments: segments.map((s) => ({ ...s, pct: gross > 0 ? (s.value / gross) * 100 : 0 })),
    total,
    installment,
    // What the position looks like with the loans set aside — the figure the
    // runway and savings ratios already reason about, since a house is not
    // spendable and its mortgage is not a bill you can choose to skip.
    withoutLoans: installment > 0 ? total + installment : null,
    installmentShareOfDebt:
      revolving + installment > 0
        ? Math.round((installment / (revolving + installment)) * 100)
        : null,
  };
}

// "$138,000 liquid" — the total less the property and vehicles inside it, or
// null when the household owns none and the distinction would be noise.
export function liquidLabel(summary, fallbackTotal = null) {
  const realAssets = summary?.total_real_assets ?? 0;
  const total = summary?.net_worth ?? fallbackTotal;
  if (realAssets <= 0 || total === null || total === undefined) return null;
  return `${WHOLE_DOLLARS.format(total - realAssets)} liquid`;
}
