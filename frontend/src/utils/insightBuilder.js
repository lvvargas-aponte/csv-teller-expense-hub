// Build curated "insight cards" from data already loaded by FinancesPage.
// Each rule guards itself; if data is missing, that rule is skipped. The
// caller falls back to a neutral nudge if buildInsights returns [].

const TAG_COLORS = {
  red:   { bg: '#fee2e2', cls: 'ov-tag-red' },
  amber: { bg: '#fef3c7', cls: 'ov-tag-amber' },
  green: { bg: '#d1fae5', cls: 'ov-tag-green' },
  blue:  { bg: '#dbeafe', cls: 'ov-tag-blue' },
};

// rule output shape:
// { id, icon, iconBg, tag, tagClass, title, body, action }
//
// `action` is { label, target } where target is one of:
//   { route: '/' }                          → navigate via react-router
//   { financesTab: 'transactions' }         → switch active tab inside FinancesPage
//   { route: '/finances', tab: 'accounts' } → both
//
// FinancesPage owns the click handler and decides what to do.

const fmt$ = (n) => '$' + (Math.abs(parseFloat(n) || 0)).toLocaleString('en-US', {
  minimumFractionDigits: 0, maximumFractionDigits: 0,
});

function currentMonthKey(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function txnMonth(t) {
  if (!t?.date) return null;
  const m = /^(\d{4})-(\d{2})/.exec(t.date);
  return m ? `${m[1]}-${m[2]}` : null;
}

// ── Rule 1: Large uncategorized spending ──────────────────────────────────────
// Trigger: this month's debit-without-category total > $500 OR > 20% of month spend.
function ruleUncategorized(transactions) {
  if (!Array.isArray(transactions) || transactions.length === 0) return null;
  const monthKey = currentMonthKey();
  let total = 0;
  let uncat = 0;
  for (const t of transactions) {
    if (txnMonth(t) !== monthKey) continue;
    if ((t.transaction_type || 'debit') !== 'debit') continue;
    const amt = Math.abs(parseFloat(t.amount) || 0);
    total += amt;
    if (!t.category || String(t.category).trim() === '') uncat += amt;
  }
  if (uncat < 500 && (total === 0 || uncat / total < 0.2)) return null;
  return {
    id: 'uncategorized',
    icon: '📦',
    iconBg: TAG_COLORS.red.bg,
    tag: 'Action needed',
    tagClass: TAG_COLORS.red.cls,
    title: 'Large uncategorized spending',
    body: `${fmt$(uncat)} of your spending this month has no category. ` +
          `Tagging these transactions gives you a clearer picture of where your money goes.`,
    action: { label: 'Categorize transactions →', target: { route: '/' } },
  };
}

// ── Rule 2: Expenses exceeded prior month ─────────────────────────────────────
// Uses dashboard.monthly_totals. If the latest month's spend is materially higher
// than the prior month, surface as "Heads up". Income data isn't always available;
// if it is via summary or dashboard, prefer the income vs. expense framing.
function ruleSpendingHigh(dashboard) {
  const totals = dashboard?.monthly_totals;
  if (!Array.isArray(totals) || totals.length < 2) return null;
  const last = totals[totals.length - 1] || {};
  const prev = totals[totals.length - 2] || {};
  const lastTotal = parseFloat(last.total) || 0;
  const prevTotal = parseFloat(prev.total) || 0;
  if (prevTotal <= 0) return null;
  const delta = lastTotal - prevTotal;
  if (delta < prevTotal * 0.1) return null;  // require >= 10% jump
  return {
    id: 'spending-high',
    icon: '📉',
    iconBg: TAG_COLORS.amber.bg,
    tag: 'Heads up',
    tagClass: TAG_COLORS.amber.cls,
    title: `Spending up ${fmt$(delta)} vs. prior month`,
    body: `${last.month || 'This month'} spend (${fmt$(lastTotal)}) is higher than ` +
          `${prev.month || 'last month'} (${fmt$(prevTotal)}). Worth a look at what changed.`,
    action: { label: 'Review spending →', target: { route: '/' } },
  };
}

// ── Rule 3: Net worth up this quarter ─────────────────────────────────────────
function ruleNetWorthUp(dashboard) {
  const trend = dashboard?.balance_trend;
  if (!trend) return null;
  const delta = parseFloat(trend.delta_30d ?? 0);
  if (delta <= 0) return null;
  // Best-effort quarterly delta: prefer delta_90d if backend provides it,
  // otherwise extrapolate from the 30-day delta as a rough estimate.
  const quarterly = parseFloat(trend.delta_90d ?? delta * 3);
  return {
    id: 'net-worth-up',
    icon: '🎉',
    iconBg: TAG_COLORS.green.bg,
    tag: 'Win',
    tagClass: TAG_COLORS.green.cls,
    title: `Net worth up ${fmt$(quarterly)} this quarter`,
    body: `Your net worth has improved by ${fmt$(delta)} over the past 30 days — ` +
          `consistent progress. Keep paying down debt and building cash.`,
    action: null,
  };
}

// ── Rule 4: Largest credit card balance ───────────────────────────────────────
function ruleLargestBalance(summary, accountDetails = {}) {
  const accounts = summary?.accounts || [];
  const credit = accounts.filter((a) => a.type === 'credit');
  if (credit.length === 0) return null;
  // ledger represents balance owed for credit accounts in this app's shape.
  let biggest = null;
  for (const a of credit) {
    const owed = Math.abs(parseFloat(a.ledger) || 0);
    if (!biggest || owed > biggest._owed) biggest = { ...a, _owed: owed };
  }
  if (!biggest || biggest._owed <= 0) return null;
  const apr = parseFloat(accountDetails[biggest.id]?.apr) || null;
  const monthlyInterest = apr ? Math.round((biggest._owed * (apr / 100)) / 12) : null;
  return {
    id: 'largest-balance',
    icon: '💳',
    iconBg: TAG_COLORS.blue.bg,
    tag: 'Insight',
    tagClass: TAG_COLORS.blue.cls,
    title: `${biggest.name} is your biggest card balance`,
    body: `${fmt$(biggest._owed)} owed on ${biggest.name}` +
          (biggest.institution ? ` (${biggest.institution})` : '') +
          '.' +
          ((monthlyInterest !== null && monthlyInterest !== undefined)
            ? ` At ${apr}% APR, that costs about ${fmt$(monthlyInterest)}/month in interest. ` +
              `Prioritizing this in your payoff plan saves the most.`
            : ' Add an APR in the Debt Payoff Planner below to see what it costs you each month.'),
    action: { label: 'See payoff plan →', target: { financesTab: 'overview' } },
  };
}

export function buildInsights({ summary, dashboard, transactions, accountDetails } = {}) {
  const out = [];
  const r1 = ruleUncategorized(transactions);   if (r1) out.push(r1);
  const r2 = ruleSpendingHigh(dashboard);        if (r2) out.push(r2);
  const r3 = ruleNetWorthUp(dashboard);          if (r3) out.push(r3);
  const r4 = ruleLargestBalance(summary, accountDetails); if (r4) out.push(r4);
  return out;
}