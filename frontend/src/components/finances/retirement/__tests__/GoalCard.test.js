import React from 'react';
import { render, screen } from '@testing-library/react';
import GoalCard from '../GoalCard';

const goal = (overrides = {}) => ({
  basis: 'today',
  annual_spending: 60000,
  gross_target: 1764705.89,
  rental_offset: 0,
  social_security_offset: 0,
  social_security_pending: false,
  social_security_start_age: 67,
  fund_from_investments: 60000,
  effective_withdrawal_rate_pct: 3.4,
  target: 1764705.89,
  multiple: 29.4,
  current_balance: 441176.47,
  gap: 1323529.42,
  funded_pct: 25,
  fully_funded: false,
  after_payoff: null,
  ...overrides,
});

const afterPayoff = {
  rental_offset: 33825.6,
  fund_from_investments: 26174.4,
  target: 769835.3,
  reduction: 858705.88,
  final_payoff_year: 2054,
  final_payoff_age: 68,
};

// Amounts render inside a <Num> span with the unit as a sibling, so row
// assertions read the whole row rather than one exact string.
const row = (label) => screen.getByText(label).closest('.prop-row');

test('shows the target, the multiple and the progress', () => {
  const { container } = render(<GoalCard goal={goal()} />);
  expect(container.querySelector('.ret-goal-target-value'))
    .toHaveTextContent('$1,764,705.89');
  expect(screen.getByText('29.4× your annual spending')).toBeInTheDocument();
  expect(screen.getByText('25%')).toBeInTheDocument();

  const bar = screen.getByRole('progressbar');
  expect(bar).toHaveAttribute('aria-valuenow', '25');
  expect(bar.firstChild).toHaveStyle({ width: '25%' });
});

test('renders nothing when there is no spending figure to build one from', () => {
  const { container } = render(<GoalCard goal={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('subtracts rental profit and says what it is worth', () => {
  render(<GoalCard goal={goal({
    rental_offset: 24000,
    fund_from_investments: 36000,
    target: 1058823.53,
  })} />);
  expect(row('Less rental profit')).toHaveTextContent('−$24,000.00/yr');
  expect(row('Investments must fund')).toHaveTextContent('$36,000.00/yr');
  // The gross figure is shown so the properties' contribution is visible.
  expect(screen.getByText(/Without the rentals/)).toHaveTextContent('$1,764,705.89');
});

test('explains that Social Security is not yet subtracted', () => {
  render(<GoalCard goal={goal({ social_security_pending: true })} />);
  expect(screen.getByText(/starts at age 67/)).toBeInTheDocument();
  expect(screen.queryByText('Less Social Security')).not.toBeInTheDocument();
});

test('subtracts Social Security once it is being drawn', () => {
  render(<GoalCard goal={goal({
    social_security_offset: 24000,
    fund_from_investments: 36000,
  })} />);
  expect(screen.getByText('Less Social Security')).toBeInTheDocument();
});

describe('once the mortgages are done', () => {
  test('shows the lower target, the year and the saving', () => {
    const { container } = render(<GoalCard goal={goal({
      rental_offset: 4629.6, after_payoff: afterPayoff,
    })} />);
    expect(screen.getByText(/Once the mortgages are done · 2054, age 68/))
      .toBeInTheDocument();
    expect(container.querySelector('.ret-goal-payoff-value'))
      .toHaveTextContent('$769,835.30');
    expect(container.querySelector('.ret-goal-payoff-delta'))
      .toHaveTextContent('−$858,705.88');
    // The contrast is the point: what the rentals pay now vs. once they're free.
    expect(container.querySelector('.ret-goal-payoff-body'))
      .toHaveTextContent('$33,825.60/yr instead of $4,629.60');
  });

  test('relabels the headline so the two targets cannot be confused', () => {
    render(<GoalCard goal={goal({ after_payoff: afterPayoff })} />);
    expect(screen.getByText('Target while the mortgages run')).toBeInTheDocument();
  });

  test('labels the headline plainly when there is nothing to pay off', () => {
    render(<GoalCard goal={goal()} />);
    expect(screen.getByText('Target')).toBeInTheDocument();
    expect(screen.queryByText(/Once the mortgages are done/)).not.toBeInTheDocument();
  });
});

test('reports a funded goal without a gap to chase', () => {
  render(<GoalCard goal={goal({
    funded_pct: 100, gap: 0, fully_funded: true, current_balance: 2000000,
  })} />);
  expect(screen.getByText(/the portfolio covers it/)).toBeInTheDocument();
  expect(screen.queryByText(/to go/)).not.toBeInTheDocument();
});
