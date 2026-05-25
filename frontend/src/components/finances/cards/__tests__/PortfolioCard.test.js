import React from 'react';
import { render, screen } from '@testing-library/react';
import axios from 'axios';
import PortfolioCard from '../PortfolioCard';

jest.mock('axios');
jest.mock('../../../ui/Spin', () => () => <span data-testid="spin" />);

beforeEach(() => jest.clearAllMocks());

test('renders portfolio totals and top holdings', async () => {
  axios.get.mockResolvedValue({
    data: {
      total_value: 22000,
      total_gain: 5500,
      total_gain_pct: 33.3,
      holding_count: 2,
      allocation: [{ asset_type: 'crypto', value: 20000, pct: 91 }],
      concentration: [{ symbol: 'BTC', value: 20000, pct: 91 }],
    },
  });
  render(<PortfolioCard />);
  expect(await screen.findByText('Investment Portfolio')).toBeInTheDocument();
  expect(await screen.findByText('BTC')).toBeInTheDocument();
});

test('shows the empty state with no holdings', async () => {
  axios.get.mockResolvedValue({
    data: { holding_count: 0, total_value: 0, allocation: [], concentration: [] },
  });
  render(<PortfolioCard />);
  expect(await screen.findByText(/No holdings yet/i)).toBeInTheDocument();
});
