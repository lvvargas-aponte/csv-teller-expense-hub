import React from 'react';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import InvestmentsTab from '../InvestmentsTab';

jest.mock('axios');
jest.mock('../../ui/Spin', () => () => <span data-testid="spin" />);

const portfolioWithHoldings = {
  total_value: 22000,
  total_cost: 16500,
  total_gain: 5500,
  total_gain_pct: 33.33,
  holding_count: 2,
  allocation: [
    { asset_type: 'crypto', value: 20000, pct: 90.9 },
    { asset_type: 'stock', value: 2000, pct: 9.1 },
  ],
  concentration: [],
  by_account: [],
  holdings: [
    {
      account_id: 'a1', account_name: 'Robinhood Individual', institution: 'Robinhood',
      symbol: 'AAPL', description: 'Apple Inc.', asset_type: 'stock', quantity: 10,
      average_purchase_price: 150, last_price: 200, market_value: 2000,
      cost_basis: 1500, unrealized_gain: 500, gain_pct: 33.3,
    },
    {
      account_id: 'a1', account_name: 'Robinhood Individual', institution: 'Robinhood',
      symbol: 'BTC', description: 'Bitcoin', asset_type: 'crypto', quantity: 0.5,
      average_purchase_price: 30000, last_price: 40000, market_value: 20000,
      cost_basis: 15000, unrealized_gain: 5000, gain_pct: 33.3,
    },
  ],
};

function mockGet(config, portfolio, { accounts = [], details = {} } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/config/snaptrade')) return Promise.resolve({ data: config });
    if (url.includes('/api/investments/portfolio')) return Promise.resolve({ data: portfolio });
    if (url.includes('/api/snaptrade/connections')) {
      return Promise.resolve({ data: { connections: [] } });
    }
    if (url.includes('/api/balances/summary')) return Promise.resolve({ data: { accounts } });
    if (url.includes('/api/accounts/details')) return Promise.resolve({ data: details });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
  axios.put.mockResolvedValue({ data: {} });
}

beforeEach(() => jest.clearAllMocks());

test('shows the not-configured message when SnapTrade keys are missing', async () => {
  mockGet({ configured: false }, null);
  render(<InvestmentsTab />);
  expect(await screen.findByText('SNAPTRADE_CLIENT_ID')).toBeInTheDocument();
});

test('renders holdings grouped by account when configured', async () => {
  mockGet({ configured: true, connected: true }, portfolioWithHoldings);
  render(<InvestmentsTab />);
  expect(await screen.findByText('AAPL')).toBeInTheDocument();
  expect(screen.getByText('BTC')).toBeInTheDocument();
  expect(screen.getByText('Robinhood Individual')).toBeInTheDocument();
});

test('shows the empty state when there are no holdings', async () => {
  mockGet(
    { configured: true, connected: false },
    { holding_count: 0, total_value: 0, holdings: [], allocation: [], concentration: [], by_account: [] },
  );
  render(<InvestmentsTab />);
  expect(await screen.findByText(/No holdings yet/i)).toBeInTheDocument();
});

// Gain and loss are red vs green in the holdings table. The sign is the first
// redundant channel and a word is the second — neither may be dropped.
test('a losing holding says it is a loss, not only in red', async () => {
  mockGet({ configured: true, connected: true }, {
    ...portfolioWithHoldings,
    total_gain: -500,
    total_gain_pct: -3.03,
    holdings: [{
      ...portfolioWithHoldings.holdings[0],
      unrealized_gain: -500, gain_pct: -25,
    }],
  });
  render(<InvestmentsTab />);

  const row = await screen.findByRole('row', { name: /AAPL/ });
  expect(row).toHaveTextContent('-$500.00');
  expect(row).toHaveTextContent(/loss/i);
});

test('a winning holding keeps its plus sign and says gain', async () => {
  mockGet({ configured: true, connected: true }, portfolioWithHoldings);
  render(<InvestmentsTab />);

  const row = await screen.findByRole('row', { name: /AAPL/ });
  expect(row).toHaveTextContent('+$500.00');
  expect(row).toHaveTextContent(/gain/i);
});

// A data table with unnamed, unscoped headers is unnavigable by screen
// reader: the columns never announce alongside the cells.
test('the holdings table names itself and scopes its column headers', async () => {
  mockGet({ configured: true, connected: true }, portfolioWithHoldings);
  render(<InvestmentsTab />);

  const table = await screen.findByRole('table', { name: /holdings/i });
  const headers = within(table).getAllByRole('columnheader');
  expect(headers.length).toBeGreaterThan(0);
  headers.forEach((h) => expect(h).toHaveAttribute('scope', 'col'));
});

// --- Tax treatment ----------------------------------------------------------
// Retired from AccountsTab when Phase 3 Task 3 collapsed the Investments
// group to a summary. It feeds the after-tax net-worth calculation, so it
// needed a new home rather than disappearing — this is it.
const investmentAccount = (over = {}) => ({
  id: 'a1',
  institution: 'Robinhood',
  name: 'Robinhood Individual',
  type: 'investment',
  subtype: 'brokerage',
  tax_treatment: 'taxable',
  tax_treatment_inferred: 'taxable',
  tax_treatment_set_by_user: false,
  ...over,
});

test('a tax-treatment control renders for an investment account, marked as assumed', async () => {
  mockGet({ configured: true, connected: true }, portfolioWithHoldings, {
    accounts: [investmentAccount()],
  });
  render(<InvestmentsTab />);

  const picker = await screen.findByLabelText(/tax treatment, for robinhood individual/i);
  expect(picker).toHaveValue('taxable');
  expect(screen.getByText(/assumed taxable/i)).toBeInTheDocument();
});

test('choosing a treatment persists it against the account', async () => {
  const user = userEvent.setup();
  mockGet({ configured: true, connected: true }, portfolioWithHoldings, {
    accounts: [investmentAccount()],
  });
  render(<InvestmentsTab />);

  const picker = await screen.findByLabelText(/tax treatment, for robinhood individual/i);
  await user.selectOptions(picker, 'roth');

  await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
    expect.stringContaining('/api/accounts/a1/details'),
    expect.objectContaining({ tax_treatment: 'roth' }),
  ));
  // A confirmed choice drops the "assumed" marker.
  expect(screen.queryByText(/assumed/i)).not.toBeInTheDocument();
});
