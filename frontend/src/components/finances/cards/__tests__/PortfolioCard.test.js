import React from 'react';
import { render, screen, within } from '@testing-library/react';
import axios from 'axios';
import PortfolioCard from '../PortfolioCard';

jest.mock('axios');
jest.mock('../../../ui/Spin', () => () => <span data-testid="spin" />);

// recharts' ResponsiveContainer measures its parent via ResizeObserver,
// which reports 0x0 in jsdom — so the chart (and the symbol labels this
// test asserts on) renders nothing. Hand the chart explicit dimensions.
jest.mock('recharts', () => {
  const Original = jest.requireActual('recharts');
  const ReactLib = jest.requireActual('react');
  return {
    ...Original,
    ResponsiveContainer: ({ children }) =>
      ReactLib.cloneElement(ReactLib.Children.only(children), {
        width: 400,
        height: 300,
      }),
  };
});

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
  const { container } = render(<PortfolioCard />);
  expect(await screen.findByText('Investment Portfolio')).toBeInTheDocument();
  // Scope to the render container: recharts also writes the label into an
  // off-screen #recharts_measurement_span for text sizing, and that span is
  // appended to document.body — so a bare screen query matches twice.
  expect(await within(container).findByText('BTC')).toBeInTheDocument();
});

test('shows the empty state with no holdings', async () => {
  axios.get.mockResolvedValue({
    data: { holding_count: 0, total_value: 0, allocation: [], concentration: [] },
  });
  render(<PortfolioCard />);
  expect(await screen.findByText(/No holdings yet/i)).toBeInTheDocument();
});
