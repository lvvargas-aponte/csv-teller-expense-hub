import { buildInsights } from '../insightBuilder';

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