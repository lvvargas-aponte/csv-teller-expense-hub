// Build curated "insight cards" from data already loaded by FinancesPage.
// Each rule guards itself; if data is missing, that rule is skipped. The
// caller falls back to a neutral nudge if buildInsights returns [].

const TAG_COLORS = {
  red:   { bg: 'var(--bad-wash)',   cls: 'ov-tag-red' },
  amber: { bg: 'var(--warn-wash)',  cls: 'ov-tag-amber' },
  green: { bg: 'var(--good-wash)',  cls: 'ov-tag-green' },
  blue:  { bg: 'var(--brand-wash)', cls: 'ov-tag-blue' },
};

function titleCase(s) {
  return String(s)
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}

// rule output shape:
// { id, icon, iconBg, tag, tagClass, title, body, action }
//
// `action` is { label, target } where target is one of:
//   { route: '/transactions' }      → navigate via react-router to a real path
//   { financesTab: 'accounts' }     → navigate via the legacy tab-id → path table
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

// Categories that move money between the household's own pockets. Mirrors the
// backend's _NON_SPENDING_CATEGORIES; a card payment is not spending twice.
const NON_SPENDING_CATEGORIES = new Set([
  'credit card payment', 'credit card payments', 'card payment',
  'transfer', 'transfers', 'zelle', 'zelle out', 'venmo', 'payment',
]);

// The same gate the backend's `_is_expense` applies: a tagged transfer drops
// out, a known non-spending category drops out, and what's left counts only
// when the money-flow direction is outflow.
function isExpense(t) {
  if (t.transfer_to_account_id) return false;
  const category = String(t.category || '').trim().toLowerCase();
  if (NON_SPENDING_CATEGORIES.has(category)) return false;
  const direction = t.direction
    || ((t.transaction_type || 'debit') === 'debit' ? 'outflow' : 'inflow');
  return direction === 'outflow';
}

// ── Rule 1: Large uncategorized spending ──────────────────────────────────────
// Trigger: this month's uncategorized spend > $500 OR > 20% of month spend.
function ruleUncategorized(transactions) {
  if (!Array.isArray(transactions) || transactions.length === 0) return null;
  const monthKey = currentMonthKey();
  let total = 0;
  let uncat = 0;
  for (const t of transactions) {
    if (txnMonth(t) !== monthKey) continue;
    if (!isExpense(t)) continue;
    const amt = Math.abs(parseFloat(t.amount) || 0);
    total += amt;
    if (!t.category || String(t.category).trim() === '') uncat += amt;
  }
  if (uncat < 500 && (total === 0 || uncat / total < 0.2)) return null;
  return {
    id: 'uncategorized',
    icon: 'tag',
    iconBg: TAG_COLORS.red.bg,
    tag: 'Action needed',
    tagClass: TAG_COLORS.red.cls,
    title: 'Large uncategorized spending',
    body: `${fmt$(uncat)} of your spending this month has no category. ` +
          `Tagging these transactions gives you a clearer picture of where your money goes.`,
    action: { label: 'Categorize transactions →', target: { route: '/transactions' } },
    priority: 90,
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
    icon: 'warning',
    iconBg: TAG_COLORS.amber.bg,
    tag: 'Heads up',
    tagClass: TAG_COLORS.amber.cls,
    title: `Spending up ${fmt$(delta)} vs. prior month`,
    body: `${last.month || 'This month'} spend (${fmt$(lastTotal)}) is higher than ` +
          `${prev.month || 'last month'} (${fmt$(prevTotal)}). Worth a look at what changed.`,
    action: { label: 'Review spending →', target: { route: '/transactions' } },
    priority: 60,
  };
}

// ── Rule 3: Net worth trending up ─────────────────────────────────────────
function ruleNetWorthUp(dashboard) {
  const trend = dashboard?.balance_trend;
  if (!trend) return null;
  const delta = parseFloat(trend.delta_30d ?? 0);
  if (delta <= 0) return null;
  // Only claim a quarter when there is a real 90-day delta. Tripling the
  // 30-day figure headlined a number the household never earned.
  const quarterly = trend.delta_90d === null || trend.delta_90d === undefined
    ? null
    : parseFloat(trend.delta_90d);
  const headline = quarterly !== null
    ? `Net worth up ${fmt$(quarterly)} this quarter`
    : `Net worth up ${fmt$(delta)} this month`;
  return {
    id: 'net-worth-up',
    icon: 'invest',
    iconBg: TAG_COLORS.green.bg,
    tag: 'Win',
    tagClass: TAG_COLORS.green.cls,
    title: headline,
    body: `Your net worth has improved by ${fmt$(delta)} over the past 30 days — ` +
          `consistent progress. Keep paying down debt and building cash.`,
    action: null,
    priority: 20,
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
    icon: 'accounts',
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
    action: { label: 'See payoff plan →', target: { financesTab: 'accounts' } },
    priority: 20,
  };
}

// Alerts arrive pre-sorted by severity and carry no id, so identity is the
// composite of the fields that make one alert distinct from another.
const ALERT_TAGS = {
  error: { tag: 'Action needed', color: 'red',   priority: 100, icon: 'warning' },
  warn:  { tag: 'Heads up',      color: 'amber', priority: 70,  icon: 'warning' },
  info:  { tag: 'For info',      color: 'blue',  priority: 30,  icon: 'info' },
};

function ruleAlerts(alerts) {
  if (!Array.isArray(alerts)) return [];
  return alerts.map((a) => {
    const t = ALERT_TAGS[a.severity] || ALERT_TAGS.info;
    return {
      id: `alert-${a.severity}-${a.category}-${a.message}`,
      icon: t.icon,
      iconBg: TAG_COLORS[t.color].bg,
      tag: t.tag,
      tagClass: TAG_COLORS[t.color].cls,
      title: a.category ? titleCase(a.category) : 'Alert',
      body: a.message,
      action: a.tab ? { label: 'Take a look →', target: { financesTab: a.tab } } : null,
      priority: t.priority,
    };
  });
}

// The digest's own `alerts` array is collect_alerts() truncated — the same rows
// /api/alerts returns, only staler. Only the parts with no other home are read.
function ruleSubscriptionPriceHikes(digest) {
  const hikes = digest?.payload?.subscriptions?.price_increases;
  if (!Array.isArray(hikes) || hikes.length === 0) return [];
  return hikes.map((h) => ({
    id: `sub-hike-${h.merchant_key}`,
    icon: 'calendar',
    iconBg: TAG_COLORS.amber.bg,
    tag: 'Heads up',
    tagClass: TAG_COLORS.amber.cls,
    title: 'Subscription price went up',
    body: `${h.sample_description} rose ${Math.round(h.price_change_pct)}% to ` +
          `${fmt$(h.latest_amount)}. Worth deciding whether to keep it.`,
    action: { label: 'Review subscriptions →', target: { route: '/plan/commitments/recurring' } },
    priority: 65,
  }));
}

// ── Week-over-week spending jump (digest) ──────────────────────────────────
// _week_over_week_spending in backend/digest.py returns
// { this_week, prior_week, change_pct, top_categories: [{category, amount}] }.
// change_pct is null when there was no prior-week spend to compare against.
function ruleDigestSpending(digest) {
  const spend = digest?.payload?.spending;
  if (!spend || spend.change_pct === null || spend.change_pct === undefined) return null;
  if (spend.change_pct < 20) return null;
  const topCat = Array.isArray(spend.top_categories) ? spend.top_categories[0] : null;
  return {
    id: 'digest-spending-up',
    icon: 'warning',
    iconBg: TAG_COLORS.amber.bg,
    tag: 'Heads up',
    tagClass: TAG_COLORS.amber.cls,
    title: `Spending up ${Math.round(spend.change_pct)}% this week`,
    body: `You spent ${fmt$(spend.this_week)} this week vs. ${fmt$(spend.prior_week)} last week` +
          (topCat ? `, led by ${topCat.category} (${fmt$(topCat.amount)}).` : '.'),
    action: { label: 'Review spending →', target: { route: '/transactions' } },
    priority: 55,
  };
}

export function buildInsights({ summary, dashboard, transactions, accountDetails, alerts, digest } = {}) {
  const out = [];
  out.push(...ruleAlerts(alerts));
  out.push(...ruleSubscriptionPriceHikes(digest));
  const r1 = ruleUncategorized(transactions);   if (r1) out.push(r1);
  const r2 = ruleSpendingHigh(dashboard);        if (r2) out.push(r2);
  const r3 = ruleNetWorthUp(dashboard);          if (r3) out.push(r3);
  const r4 = ruleLargestBalance(summary, accountDetails); if (r4) out.push(r4);
  const r5 = ruleDigestSpending(digest);         if (r5) out.push(r5);
  return out.sort((a, b) => b.priority - a.priority);
}
