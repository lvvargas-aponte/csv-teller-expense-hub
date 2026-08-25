import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

test('the liquid figure explains why the runway ignores property', async () => {
  const user = userEvent.setup();
  render(<NetWorthCard dashboard={dashboard} summary={summary} />);

  await user.click(screen.getByRole('button', { name: 'About liquid net worth' }));

  expect(screen.getByRole('note'))
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

const afterTax = {
  available: true,
  headline_net_worth: 588000,
  after_tax_net_worth: 539000,
  deferred_tax_estimate: 49000,
  pre_tax_balance: 222727,
  rate_pct: 22,
  rate_source: 'profile',
  note: 'Estimate. Pre-tax balances discounted at your stated marginal rate.',
};

test('the after-tax figure is a hedged secondary line, never the headline', () => {
  render(<NetWorthCard dashboard={dashboard} summary={summary} afterTax={afterTax} />);

  // "about" is not optional — the figure is an estimate off a stated rate.
  expect(screen.getByText(/about \$539,000 after deferred tax/i)).toBeInTheDocument();
  expect(screen.getByText(/discounted at your stated marginal rate/i)).toBeInTheDocument();
});

test('with the setting off the after-tax line is not rendered at all', () => {
  render(
    <NetWorthCard
      dashboard={dashboard}
      summary={summary}
      afterTax={{ available: false, reason: 'After-tax net worth is turned off.' }}
    />,
  );

  expect(screen.queryByText(/after deferred tax/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/turned off/i)).not.toBeInTheDocument();
});
