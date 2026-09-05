import { buildInsights } from '../insightBuilder';
import { ICON_NAMES as ALL_ICON_NAMES } from '../../components/ui/Icon';

const monthKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;

const txn = (over = {}) => ({
  date: `${monthKey()}-15`,
  amount: -50, transaction_type: 'debit', category: '',
  ...over,
});

test('returns empty array when no data', () => {
  expect(buildInsights({})).toEqual([]);
});

test('uncategorized rule fires when uncat > $500', () => {
  const transactions = Array.from({ length: 12 }, () => txn({ amount: -50, category: '' }));
  const out = buildInsights({ transactions });
  expect(out.find((c) => c.id === 'uncategorized')).toBeTruthy();
});

test('uncategorized rule does NOT fire when everything is categorized', () => {
  const transactions = [txn({ amount: -1000, category: 'Groceries' })];
  const out = buildInsights({ transactions });
  expect(out.find((c) => c.id === 'uncategorized')).toBeFalsy();
});

test('spending-high rule fires on >10% jump month-over-month', () => {
  const dashboard = { monthly_totals: [
    { month: 'Mar', total: 1000 },
    { month: 'Apr', total: 1500 },
  ]};
  const out = buildInsights({ dashboard });
  expect(out.find((c) => c.id === 'spending-high')).toBeTruthy();
});

test('spending-high rule does NOT fire on a small change', () => {
  const dashboard = { monthly_totals: [
    { month: 'Mar', total: 1000 },
    { month: 'Apr', total: 1050 },
  ]};
  const out = buildInsights({ dashboard });
  expect(out.find((c) => c.id === 'spending-high')).toBeFalsy();
});

test('net-worth-up rule fires only when delta_30d > 0', () => {
  const positive = buildInsights({ dashboard: { balance_trend: { delta_30d: 800, delta_90d: 2000 } } });
  expect(positive.find((c) => c.id === 'net-worth-up')).toBeTruthy();

  const negative = buildInsights({ dashboard: { balance_trend: { delta_30d: -500 } } });
  expect(negative.find((c) => c.id === 'net-worth-up')).toBeFalsy();
});

test('largest-balance rule picks the credit account with the highest |ledger|', () => {
  const summary = { accounts: [
    { id: 'a1', type: 'credit', name: 'Card A', institution: 'Chase',    ledger: -1200 },
    { id: 'a2', type: 'credit', name: 'Card B', institution: 'Discover', ledger: -3500 },
    { id: 'a3', type: 'depository', name: 'Checking', ledger: 5000 },
  ]};
  const accountDetails = { a2: { apr: 24 } };
  const out = buildInsights({ summary, accountDetails });
  const card = out.find((c) => c.id === 'largest-balance');
  expect(card).toBeTruthy();
  expect(card.title).toMatch(/Card B/);
  expect(card.body).toMatch(/24% APR/);
});

test('largest-balance rule skips when there are no credit accounts', () => {
  const summary = { accounts: [{ id: 'a1', type: 'depository', ledger: 5000 }] };
  const out = buildInsights({ summary });
  expect(out.find((c) => c.id === 'largest-balance')).toBeFalsy();
});

// ── The two rule bugs the Finances remediation fixed ────────────────────────

const expenseTxn = (over = {}) => ({
  id: 't1', date: `${monthKey()}-15`, amount: 600,
  category: '', transaction_type: 'debit', direction: 'outflow', ...over,
});

const uncategorizedCard = (transactions) =>
  buildInsights({ transactions }).find((c) => c.id === 'uncategorized');

test('a credit-card payment is not uncategorized spending', () => {
  // The rule filtered on transaction_type alone, so card payments and tagged
  // transfers counted as spending. It now applies the backend's _is_expense.
  expect(uncategorizedCard([expenseTxn()])).toBeTruthy();
  expect(uncategorizedCard([expenseTxn({ direction: 'inflow' })])).toBeFalsy();
  expect(uncategorizedCard([expenseTxn({ transfer_to_account_id: 'a1' })])).toBeFalsy();
  expect(uncategorizedCard([expenseTxn({ category: 'Credit Card Payment' })])).toBeFalsy();
});

const netWorthCard = (balance_trend) =>
  buildInsights({ dashboard: { balance_trend } }).find((c) => c.id === 'net-worth-up');

test('a real 90-day delta is reported as the quarter', () => {
  const card = netWorthCard({ delta_30d: 400, delta_90d: 1500, current_net_worth: 50000 });
  expect(card.title).toMatch(/\$1,500 this quarter/);
});

test('without a 90-day delta it says this month, not a tripled guess', () => {
  const card = netWorthCard({ delta_30d: 400, current_net_worth: 50000 });
  expect(card.title).toMatch(/\$400 this month/);
  expect(card.title).not.toMatch(/quarter/);
  expect(card.title).not.toMatch(/1,200/);
});

const alert = (severity, category, message, tab) => ({ severity, category, message, tab });
const digest = (payload) => ({ id: 1, read: false, payload });

describe('buildInsights — alerts', () => {
  test('turns each alert into an insight, error before warn before info', () => {
    const out = buildInsights({
      alerts: [
        alert('info',  'cashflow', 'Cash dips below zero in 12 days', 'accounts'),
        alert('error', 'budget',   'Dining is $80 over its cap',      'budgets'),
        alert('warn',  'credit',   'Visa utilization at 61%',         'accounts'),
      ],
    });
    const ranks = out.map((i) => i.tag);
    expect(ranks.indexOf('Action needed')).toBeLessThan(ranks.indexOf('Heads up'));
    expect(out.map((i) => i.body)).toEqual([
      'Dining is $80 over its cap',
      'Visa utilization at 61%',
      'Cash dips below zero in 12 days',
    ]);
  });

  test('gives alerts stable ids without an id field on the payload', () => {
    const one = buildInsights({ alerts: [alert('warn', 'budget', 'Same text', 'budgets')] });
    const two = buildInsights({ alerts: [alert('warn', 'budget', 'Same text', 'budgets')] });
    expect(one[0].id).toBe(two[0].id);
    expect(one[0].id).toEqual(expect.any(String));
  });

  test('routes an alert through its tab, not a hardcoded path', () => {
    const [i] = buildInsights({ alerts: [alert('warn', 'budget', 'x', 'budgets')] });
    expect(i.action.target).toEqual({ financesTab: 'budgets' });
  });

  test('an alert with no tab produces no action', () => {
    const [i] = buildInsights({ alerts: [alert('info', 'cashflow', 'x', null)] });
    expect(i.action).toBeNull();
  });
});

describe('buildInsights — digest', () => {

  test('ignores the digest alerts array, which duplicates /api/alerts', () => {
    const dup = alert('error', 'budget', 'Dining is $80 over its cap', 'budgets');
    const out = buildInsights({ alerts: [dup], digest: digest({ alerts: [dup] }) });
    expect(out.filter((i) => i.body === 'Dining is $80 over its cap')).toHaveLength(1);
  });

  test('surfaces a subscription price hike from the digest', () => {
    const out = buildInsights({
      digest: digest({
        subscriptions: {
          price_increases: [
            { merchant_key: 'netflix', sample_description: 'NETFLIX.COM', price_change_pct: 14.0, latest_amount: 22.99 },
          ],
        },
      }),
    });
    const hike = out.find((i) => i.id.startsWith('sub-hike'));
    expect(hike).toBeTruthy();
    expect(hike.body).toMatch(/NETFLIX\.COM/);
  });

  test('no digest and no alerts still returns the pure-data rules', () => {
    expect(() => buildInsights({})).not.toThrow();
    expect(Array.isArray(buildInsights({}))).toBe(true);
  });

  test('fires the week-over-week spending rule right at a 20% jump', () => {
    const out = buildInsights({
      digest: digest({ spending: { change_pct: 20, this_week: 120, prior_week: 100, top_categories: [] } }),
    });
    expect(out.find((i) => i.id === 'digest-spending-up')).toBeTruthy();
  });

  test('does not fire the week-over-week spending rule just under a 20% jump', () => {
    const out = buildInsights({
      digest: digest({ spending: { change_pct: 19.9, this_week: 119, prior_week: 100, top_categories: [] } }),
    });
    expect(out.find((i) => i.id === 'digest-spending-up')).toBeUndefined();
  });

  // ── A hike and its matching recurring-anomaly alert are the same underlying
  // detect_recurring_charges() row surfaced twice — collapse to one.
  test('a recurring alert that matches a subscription hike collapses to one row', () => {
    const recurringAlert = alert(
      'info', 'recurring',
      'NETFLIX.COM charged $22.99 (25% up vs. usual $18.39)', 'commitments',
    );
    const out = buildInsights({
      alerts: [recurringAlert],
      digest: digest({
        subscriptions: {
          price_increases: [
            { merchant_key: 'netflix', sample_description: 'NETFLIX.COM', price_change_pct: 25.0, latest_amount: 22.99 },
          ],
        },
      }),
    });
    const netflixRows = out.filter((i) => i.body.includes('NETFLIX.COM') || i.title.includes('Subscription'));
    expect(netflixRows).toHaveLength(1);
    expect(netflixRows[0].id.startsWith('sub-hike')).toBe(true);
  });

  test('a recurring alert with no matching hike still appears', () => {
    const recurringAlert = alert(
      'info', 'recurring',
      'SPOTIFY charged $12.99 (30% up vs. usual $9.99)', 'commitments',
    );
    const out = buildInsights({ alerts: [recurringAlert] });
    expect(out.find((i) => i.body === recurringAlert.message)).toBeTruthy();
  });

  test('the digest narrative renders as its own low-priority row', () => {
    const out = buildInsights({ digest: digest({ narrative: 'Spending was steady this week.' }) });
    const row = out.find((i) => i.id === 'digest-narrative');
    expect(row).toBeTruthy();
    expect(row.body).toBe('Spending was steady this week.');
    expect(ALL_ICON_NAMES).toContain(row.icon);
  });

  test('the digest narrative rule does not fire when narrative is missing or empty', () => {
    expect(buildInsights({ digest: digest({}) }).find((i) => i.id === 'digest-narrative')).toBeUndefined();
    expect(buildInsights({ digest: digest({ narrative: '' }) }).find((i) => i.id === 'digest-narrative')).toBeUndefined();
    expect(buildInsights({ digest: digest({ narrative: null }) }).find((i) => i.id === 'digest-narrative')).toBeUndefined();
  });
});

describe('buildInsights — duplicate alert keys', () => {
  test('two byte-identical alerts get distinct, order-stable ids', () => {
    const same = alert('warn', 'credit', 'Credit card utilization at 61% — consider paying down', 'debt');
    const out1 = buildInsights({ alerts: [same, same] });
    expect(out1[0].id).not.toBe(out1[1].id);
    const out2 = buildInsights({ alerts: [same, same] });
    expect(out1.map((i) => i.id)).toEqual(out2.map((i) => i.id));
  });
});

describe('buildInsights — presentation', () => {
  test('every insight names an Icon rather than carrying an emoji', () => {
    const out = buildInsights({ alerts: [alert('error', 'budget', 'x', 'budgets')] });
    for (const i of out) {
      expect(i.icon).toMatch(/^[a-z][a-zA-Z]*$/);
    }
  });

  test('every insight carries a numeric priority', () => {
    const out = buildInsights({ alerts: [alert('warn', 'budget', 'x', 'budgets')] });
    expect(typeof out[0].priority).toBe('number');
  });
});

describe('buildInsights — where an action lands', () => {
  test('the payoff-plan action points at Debt, where the planner lives', () => {
    const out = buildInsights({
      summary: { accounts: [{ id: 'a1', type: 'credit', name: 'JetBlue Plus', ledger: -4200 }] },
      accountDetails: { a1: { apr: 22.5 } },
    });
    const row = out.find((i) => i.id === 'largest-balance');
    expect(row.action.target).toEqual({ financesTab: 'debt' });
  });

  test('the no-APR nudge does not claim the planner is on this page', () => {
    const out = buildInsights({
      summary: { accounts: [{ id: 'a1', type: 'credit', name: 'JetBlue Plus', ledger: -4200 }] },
      accountDetails: {},
    });
    expect(out.find((i) => i.id === 'largest-balance').body).not.toMatch(/below/);
  });

  test('a price-hike action goes straight to commitments, not through a redirect', () => {
    const out = buildInsights({
      digest: digest({
        subscriptions: {
          price_increases: [
            { merchant_key: 'netflix', sample_description: 'NETFLIX.COM', price_change_pct: 14.0, latest_amount: 22.99 },
          ],
        },
      }),
    });
    expect(out.find((i) => i.id.startsWith('sub-hike')).action.target)
      .toEqual({ route: '/plan/commitments' });
  });
});

describe('buildInsights — several price hikes collapse into one row', () => {
  const threeHikes = {
    subscriptions: {
      price_increases: [
        { merchant_key: 'netflix', sample_description: 'NETFLIX.COM', price_change_pct: 14, latest_amount: 20 },
        { merchant_key: 'spotify', sample_description: 'SPOTIFY', price_change_pct: 10, latest_amount: 12 },
        { merchant_key: 'claude',  sample_description: 'CLAUDE.AI', price_change_pct: 30, latest_amount: 8 },
      ],
    },
  };

  test('three hikes make one row that names the count and the combined cost', () => {
    const rows = buildInsights({ digest: digest(threeHikes) })
      .filter((i) => i.id.startsWith('sub-hike'));
    expect(rows).toHaveLength(1);
    expect(rows[0].title).toBe('3 subscriptions went up in price');
    expect(rows[0].body).toMatch(/NETFLIX\.COM, SPOTIFY and 1 more/);
    expect(rows[0].body).toMatch(/\$40/);
  });

  test('the grouped row keeps a stable id while the same hikes stand', () => {
    const id = () => buildInsights({ digest: digest(threeHikes) })
      .find((i) => i.id.startsWith('sub-hike')).id;
    expect(id()).toBe(id());
    // Order from the backend is not guaranteed, so identity must not depend on it.
    const reversed = { subscriptions: { price_increases: [...threeHikes.subscriptions.price_increases].reverse() } };
    expect(buildInsights({ digest: digest(reversed) })
      .find((i) => i.id.startsWith('sub-hike')).id).toBe(id());
  });
});
