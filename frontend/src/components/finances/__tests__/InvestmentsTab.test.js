import React from 'react';
import { render, screen } from '@testing-library/react';
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

function mockGet(config, portfolio) {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/config/snaptrade')) return Promise.resolve({ data: config });
    if (url.includes('/api/investments/portfolio')) return Promise.resolve({ data: portfolio });
    if (url.includes('/api/snaptrade/connections')) {
      return Promise.resolve({ data: { connections: [] } });
    }
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
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
