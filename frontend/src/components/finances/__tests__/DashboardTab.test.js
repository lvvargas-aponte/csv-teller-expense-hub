import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import DashboardTab from '../DashboardTab';
import { getDashboard, getIncomeVsExpenses } from '../../../api/dashboard';
import { getBalancesSummary } from '../../../api/balances';

jest.mock('axios');
jest.mock('../../../api/dashboard');
jest.mock('../../../api/balances');

// The cards each fetch for themselves; this test is about the KPI row only.
jest.mock('../SpendingInsights', () => () => <div />);
jest.mock('../cards/StandingCard', () => () => <div />);
jest.mock('../cards/WeeklyDigestCard', () => () => <div />);
jest.mock('../cards/NetWorthCard', () => () => <div />);
jest.mock('../cards/CashFlowCard', () => () => <div />);
jest.mock('../cards/SpendingByCategoryCard', () => () => <div />);
jest.mock('../cards/IncomeVsExpensesCard', () => () => <div />);
jest.mock('../cards/BalancesCard', () => () => <div />);
jest.mock('../cards/PortfolioCard', () => () => <div />);
jest.mock('../cards/CreditUtilizationCard', () => () => <div />);
jest.mock('../cards/BudgetsCard', () => () => <div />);
jest.mock('../cards/RecurringChargesCard', () => () => <div />);
jest.mock('../cards/AlertsCard', () => () => <div />);

const spendComparison = (over = {}) => ({
  as_of_day: 10,
  current_month: '2026-08',
  current_month_to_date: 120.0,
  prior_month: '2026-07',
  prior_month_same_period: 100.0,
  prior_month_full: 500.0,
  delta: 20.0,
  pct_change: 20.0,
  current_month_is_partial: true,
  ...over,
});

const renderTab = ({ rows, comparison = spendComparison(), signals, summary = { net_worth: 0 } }) => {
  getDashboard.mockResolvedValue({
    data: {
      months: [], spending_by_month: {}, monthly_totals: [],
      net_worth_timeseries: [], recurring_charges: [],
      balance_trend: { available: false },
      spend_comparison: comparison,
    },
  });
  getIncomeVsExpenses.mockResolvedValue({ data: { months: [], rows } });
  getBalancesSummary.mockResolvedValue({ data: summary });
  return render(
    <DashboardTab healthScore={70} healthSignals={signals} summary={summary} />,
  );
};

const kpi = (label) => screen.getByRole('group', { name: label });

beforeEach(() => jest.clearAllMocks());

test('an income month still in progress renders no delta arrow', async () => {
  renderTab({
    rows: [
      { month: '2026-08', income: 900, expenses: 400, net: 500, is_partial: true },
    ],
  });

  await waitFor(() => expect(kpi('Income')).toHaveTextContent('$900.00'));
  expect(kpi('Income')).not.toHaveTextContent(/vs prior/i);
  expect(kpi('Income')).toHaveTextContent(/month in progress/i);
});

test('income and net cash flow read the most recent complete month', async () => {
  renderTab({
    rows: [
      { month: '2026-06', income: 800, expenses: 300, net: 500, is_partial: false },
      { month: '2026-07', income: 1000, expenses: 400, net: 600, is_partial: false },
      { month: '2026-08', income: 120, expenses: 60, net: 60, is_partial: true },
    ],
  });

  await waitFor(() => expect(kpi('Income')).toHaveTextContent('$1,000.00'));
  expect(kpi('Income')).toHaveTextContent(/\$200\.00\s*vs prior/);
  expect(kpi('Net Cash Flow')).toHaveTextContent('$600.00');
  expect(kpi('Net Cash Flow')).not.toHaveTextContent(/month in progress/i);
});

test('this month compares against the same stretch of the prior month', async () => {
  renderTab({ rows: [] });

  await waitFor(() => expect(kpi('This Month')).toHaveTextContent('$120.00'));
  expect(kpi('This Month')).toHaveTextContent(/\$20\.00\s*vs prior/);
  expect(kpi('This Month')).toHaveTextContent(/first 10 days of July/i);
});

// The score is renormalized over whatever had data, so the banner has to say
// how much of the model that was — otherwise a rising number is unreadable.
const signalSet = (availableCount) => [
  'emergency_runway', 'savings_rate', 'credit_utilization',
  'debt_to_income', 'net_worth_trend',
].map((key, i) => ({
  key, label: key, weight: 20, detail: 'detail', available: i < availableCount,
}));

test('the banner says how many signals the score is based on', async () => {
  renderTab({ rows: [], signals: signalSet(4) });

  await waitFor(() => {
    expect(screen.getByText('Based on 4 of 5 signals.')).toBeInTheDocument();
  });
});

test('full coverage does not clutter the banner with a caveat', async () => {
  renderTab({ rows: [], signals: signalSet(5) });

  await waitFor(() => expect(kpi('This Month')).toHaveTextContent('$120.00'));
  expect(screen.queryByText('Based on 5 of 5 signals.')).toBeNull();
});

test('balances come from the page, not a second round-trip', async () => {
  renderTab({ rows: [], summary: { net_worth: 4200 } });

  await waitFor(() => expect(kpi('Net Worth')).toHaveTextContent('$4,200.00'));
  expect(getBalancesSummary).not.toHaveBeenCalled();
});

// Real assets make "net worth" and "money you could reach" two different
// numbers. The KPI is the total, so its help text has to say what it includes
// and which of the other numbers deliberately leaves property out.
test('the net-worth KPI names the liquid figure and the runway exclusion', async () => {
  renderTab({
    rows: [],
    summary: {
      net_worth: 588000, total_cash: 18000, total_investments: 430000,
      total_real_assets: 450000, total_credit_debt: 310000,
    },
  });

  await waitFor(() => expect(kpi('Net Worth')).toBeInTheDocument());
  expect(kpi('Net Worth')).toHaveTextContent(/\$138,000 liquid/);
  expect(kpi('Net Worth')).toHaveTextContent(/runway/i);
});
