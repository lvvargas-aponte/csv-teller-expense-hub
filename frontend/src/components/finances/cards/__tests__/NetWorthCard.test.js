import React from 'react';
import { render, screen } from '@testing-library/react';
import NetWorthCard from '../NetWorthCard';

// A single number that jumps by $450,000 when a house is added, with no
// explanation of what moved, is worse than no asset support at all. The card
// has to say which of the four parts changed — and has to keep the liquid
// figure visible, because that is the one the runway ratio reasons about.
const dashboard = {
  balance_trend: { available: true, current_net_worth: 588000, delta_30d: 1200, label: 'rising' },
  net_worth_timeseries: [],
};

const summary = {
  net_worth: 588000,
  total_cash: 18000,
  total_investments: 430000,
  total_real_assets: 450000,
  total_credit_debt: 310000,
};

test('the composition is broken into cash, investments, property and debt', () => {
  render(<NetWorthCard dashboard={dashboard} summary={summary} />);

  const parts = screen.getByRole('group', { name: /what makes up net worth/i });
  expect(parts).toHaveTextContent(/Cash/);
  expect(parts).toHaveTextContent(/Investments/);
  expect(parts).toHaveTextContent(/Property/);
  expect(parts).toHaveTextContent(/Debt/);
  expect(parts).toHaveTextContent(/\$450,000/);
  expect(parts).toHaveTextContent(/-?\$310,000/);
});

test('total and liquid net worth are shown side by side', () => {
  render(<NetWorthCard dashboard={dashboard} summary={summary} />);

  // 588,000 total less the 450,000 that cannot be spent.
  expect(screen.getByText(/\$138,000 liquid/)).toBeInTheDocument();
});

test('the liquid figure explains why the runway ignores property', () => {
  render(<NetWorthCard dashboard={dashboard} summary={summary} />);

  expect(screen.getByRole('tooltip'))
    .toHaveTextContent(/emergency.*runway|runway.*ignore/i);
});

test('with no real assets the liquid line is not shown at all', () => {
  render(
    <NetWorthCard
      dashboard={dashboard}
      summary={{ ...summary, total_real_assets: 0, net_worth: 138000 }}
    />,
  );

  expect(screen.queryByText(/liquid/)).not.toBeInTheDocument();
});
