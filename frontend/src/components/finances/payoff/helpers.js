export const blankRow = () => ({
  _id: crypto.randomUUID(), accountId: null, name: '', balance: '', apr: '', min_payment: '',
  debtClass: 'credit_card', assetValue: '', dueDate: '',
  deferredInterest: false, promoApr: '', promoExpires: '',
  minPaymentFrom: '', minPaymentUntil: '',
  payoffStartBalance: '', payoffStartDate: '', paymentAccountId: '',
});

// A secured debt is one backed by an asset — a mortgage or auto loan. These
// sit out of the payoff queue on purpose: an avalanche ranks purely on APR, so
// a 7.6% mortgage would take the extra payment ahead of a 29% card, and a
// 30-year term would swamp the "paid off in" figure. They stay on the page for
// balance, APR, and equity tracking; they just don't get simulated.
export const isSecured = (row) => row.debtClass === 'loan';

// Equity only means anything once a market value is on file — an empty field
// would otherwise read as "your house is worth $0" and report the whole
// mortgage as negative equity.
export const hasAssetValue = (row) =>
  row.assetValue !== '' && row.assetValue !== null && row.assetValue !== undefined;

export const rowEquity = (row) =>
  (parseFloat(row.assetValue) || 0) - (parseFloat(row.balance) || 0);

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

// Parse an <input type="date"> value as a *local* date. `new Date('2028-06-01')`
// parses as UTC midnight, which lands on May 31 for anyone west of Greenwich —
// exactly the kind of off-by-one that would misreport a payoff deadline.
export function parseISODate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

// Whole months from `from` to `to`. Mirrors the backend's
// `_promo_window_months` (calendar months, day-of-month ignored) so the panel
// and the simulation never disagree about how long a promo window is.
export function monthsBetween(from, to) {
  return (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth());
}

// Ceiling on how far a promo simulation will walk. 100 years — far past any
// real promo, but it bounds the work when a half-typed date field yields a
// nonsense deadline.
const MAX_HORIZON_MONTHS = 1200;

// Level payment that clears `principal` in `months` at `monthlyRate`.
function annuityPayment(principal, monthlyRate, months) {
  if (months <= 0) return principal;
  if (monthlyRate <= 0) return principal / months;
  const growth = Math.pow(1 + monthlyRate, months);
  return (principal * monthlyRate * growth) / (growth - 1);
}

/**
 * Work out what a deferred-interest promo actually demands.
 *
 * The card charges `promoApr` (usually 0) while the promo runs, but if any
 * balance survives past `promoExpires` it bills back every dollar of interest
 * that *would* have accrued at the full `apr` — on the whole original balance,
 * in one hit. So the only number that matters is what you must pay per month
 * to hit zero on the deadline, and the row's minimum payment almost never is.
 *
 * Models two futures:
 *   - the user's stated plan — minimum through `minPaymentUntil`, then catch up
 *   - minimums the whole way — the miss-the-deadline case, and its retro bill
 *
 * Returns null when there isn't enough to say anything (no balance, no
 * deadline). `today` is injectable so the result is testable.
 */
export function deferredPlan(row, today = new Date()) {
  const balance  = parseFloat(row.balance) || 0;
  const deadline = parseISODate(row.promoExpires);
  if (!(balance > 0) || !deadline) return null;

  const fullRate   = (parseFloat(row.apr)      || 0) / 100 / 12;
  const promoRate  = (parseFloat(row.promoApr) || 0) / 100 / 12;
  const minPayment = parseFloat(row.min_payment) || 0;

  // Clamped because this runs on every keystroke in the date field: typing a
  // year leaves "0002-06-01" and then "2028-06-01" in transit, and an
  // unclamped horizon would spin tens of thousands of iterations per render.
  // A deferred-interest promo never runs past a century.
  const monthsToDeadline = Math.min(monthsBetween(today, deadline), MAX_HORIZON_MONTHS);
  if (monthsToDeadline <= 0) {
    return {
      balance, deadline, monthsToDeadline: 0, expired: true,
      minMonths: 0, balanceAtWindowEnd: balance, catchUpMonths: 0,
      requiredMonthly: balance, lumpSum: true,
      minCoversInterest: minPayment > balance * promoRate,
      clearedByMinimums: false, leftoverAtDeadline: balance, retroInterest: 0,
    };
  }

  // The stated plan: pay only the minimum until `minPaymentUntil`, capped at
  // the deadline itself. No end date means the catch-up starts now.
  const minUntil = parseISODate(row.minPaymentUntil);
  const minMonths = minUntil
    ? Math.min(Math.max(monthsBetween(today, minUntil), 0), monthsToDeadline)
    : 0;

  // Checked against today's balance, which is the highest it gets: a minimum
  // that outruns the interest now keeps outrunning it as the balance falls.
  // Equality counts as failing — a payment exactly equal to the interest holds
  // the balance flat forever.
  const minCoversInterest = minPayment > balance * promoRate;

  let bal = balance;
  for (let m = 0; m < minMonths && bal > 0; m += 1) {
    bal = Math.max(0, bal + bal * promoRate - minPayment);
  }
  const balanceAtWindowEnd = bal;
  const catchUpMonths = monthsToDeadline - minMonths;
  const requiredMonthly = balanceAtWindowEnd <= 0
    ? 0
    : annuityPayment(balanceAtWindowEnd, promoRate, catchUpMonths);

  // Minimums all the way — what's still owed on the deadline, and the deferred
  // interest that gets billed back if it isn't zero. The retro figure counts
  // only from today forward, because nothing here records when the promo began;
  // the real charge reaches back to the purchase date and so runs higher.
  let mb = balance;
  let retroInterest = 0;
  for (let m = 0; m < monthsToDeadline && mb > 0; m += 1) {
    retroInterest += mb * fullRate;
    mb = Math.max(0, mb + mb * promoRate - minPayment);
  }

  return {
    balance, deadline, monthsToDeadline, expired: false,
    minMonths, balanceAtWindowEnd, catchUpMonths,
    requiredMonthly,
    lumpSum: catchUpMonths <= 0 && balanceAtWindowEnd > 0,
    minCoversInterest,
    clearedByMinimums: mb <= 0,
    leftoverAtDeadline: mb,
    retroInterest,
  };
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
