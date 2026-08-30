import React from 'react';
import { render, screen } from '@testing-library/react';
import NeedsYouFeed from '../NeedsYouFeed';

jest.mock('../../../api/dashboard', () => ({ getAlerts: jest.fn() }));
jest.mock('../../../api/digest', () => ({ getLatestDigest: jest.fn(), markDigestRead: jest.fn() }));
jest.mock('../../../api/transactions', () => ({ getAllTransactions: jest.fn() }));
jest.mock('../../../api/accountDetails', () => ({ getAllAccountDetails: jest.fn() }));

const { getAlerts } = require('../../../api/dashboard');
const { getLatestDigest, markDigestRead } = require('../../../api/digest');
const { getAllTransactions } = require('../../../api/transactions');
const { getAllAccountDetails } = require('../../../api/accountDetails');

beforeEach(() => {
  jest.clearAllMocks();
  getAlerts.mockResolvedValue({ data: { alerts: [], counts: {} } });
  getLatestDigest.mockResolvedValue({ data: null });
  getAllTransactions.mockResolvedValue({ data: { transactions: [] } });
  getAllAccountDetails.mockResolvedValue({ data: {} });
});

test('renders one row per insight, most urgent first', async () => {
  getAlerts.mockResolvedValue({ data: { alerts: [
    { severity: 'warn',  category: 'credit', message: 'Visa utilization at 61%', tab: 'accounts' },
    { severity: 'error', category: 'budget', message: 'Dining is $80 over its cap', tab: 'budgets' },
  ], counts: {} } });
  render(<NeedsYouFeed />);
  const rows = await screen.findAllByRole('listitem');
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent('Dining is $80 over its cap');
});

test('says so when there is nothing to act on', async () => {
  render(<NeedsYouFeed />);
  expect(await screen.findByText(/nothing needs you/i)).toBeInTheDocument();
});

test('marks an unread digest read, once', async () => {
  getLatestDigest.mockResolvedValue({ data: { id: 7, read: false, payload: {} } });
  render(<NeedsYouFeed />);
  await screen.findByText(/nothing needs you/i);
  expect(markDigestRead).toHaveBeenCalledTimes(1);
  expect(markDigestRead).toHaveBeenCalledWith(7);
});

test('does not re-mark a digest already read', async () => {
  getLatestDigest.mockResolvedValue({ data: { id: 7, read: true, payload: {} } });
  render(<NeedsYouFeed />);
  await screen.findByText(/nothing needs you/i);
  expect(markDigestRead).not.toHaveBeenCalled();
});

test('one failed source does not blank the feed', async () => {
  getLatestDigest.mockRejectedValue(new Error('boom'));
  getAlerts.mockResolvedValue({ data: { alerts: [
    { severity: 'error', category: 'budget', message: 'Dining is $80 over its cap', tab: 'budgets' },
  ], counts: {} } });
  render(<NeedsYouFeed />);
  expect(await screen.findByText(/Dining is \$80 over its cap/)).toBeInTheDocument();
});

// ── Critical 1: summary/dashboard arrive async, after the fetch effect ─────
test('recomputes insights when summary/dashboard land after first render', async () => {
  const { rerender } = render(<NeedsYouFeed summary={null} dashboard={null} />);

  // Nothing to show yet — summary/dashboard haven't landed, and there are no
  // alerts/digest/transaction-derived rows either.
  expect(await screen.findByText(/nothing needs you/i)).toBeInTheDocument();

  // The parent's async balances/dashboard fetches resolve on a later render.
  rerender(<NeedsYouFeed
    summary={{ accounts: [
      { id: 'c1', type: 'credit', name: 'Visa', institution: 'Chase', ledger: -4200 },
    ] }}
    dashboard={{ balance_trend: { delta_30d: 500, delta_90d: 1200 } }}
  />);

  // ruleNetWorthUp and ruleLargestBalance can only fire once dashboard/summary
  // are real — if the effect closure had captured the initial nulls, neither
  // row would ever appear.
  expect(await screen.findByText(/Net worth up/i)).toBeInTheDocument();
  expect(await screen.findByText(/Visa is your biggest card balance/i)).toBeInTheDocument();
});

// ── Important 5: a total outage must not read as "all clear" ───────────────
test('an alerts-fetch failure surfaces an error, not an empty feed', async () => {
  getAlerts.mockRejectedValue(new Error('down'));
  getLatestDigest.mockRejectedValue(new Error('down'));
  getAllTransactions.mockRejectedValue(new Error('down'));
  getAllAccountDetails.mockRejectedValue(new Error('down'));

  render(<NeedsYouFeed />);

  expect(await screen.findByText(/could not load insights/i)).toBeInTheDocument();
  expect(screen.queryByText(/nothing needs you/i)).toBeNull();
});

test('a non-alerts source failing alone still renders normally, no error banner', async () => {
  getAllTransactions.mockRejectedValue(new Error('down'));
  getAlerts.mockResolvedValue({ data: { alerts: [
    { severity: 'warn', category: 'credit', message: 'Visa utilization at 61%', tab: 'accounts' },
  ], counts: {} } });

  render(<NeedsYouFeed />);

  expect(await screen.findByText('Visa utilization at 61%')).toBeInTheDocument();
  expect(screen.queryByText(/could not load insights/i)).toBeNull();
});
