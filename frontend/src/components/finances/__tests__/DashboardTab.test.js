import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DashboardTab from '../DashboardTab';
import { getDashboard, getCreditHealth } from '../../../api/dashboard';
import { getBalancesSummary } from '../../../api/balances';
import { getAfterTaxNetWorth } from '../../../api/tax';
import { getRatios } from '../../../api/health';

jest.mock('axios');
jest.mock('../../../api/dashboard');
jest.mock('../../../api/balances');
jest.mock('../../../api/tax');
jest.mock('../../../api/health');

// The cards each fetch for themselves; this test is about the hero and the
// grid membership only.
jest.mock('../NeedsYouFeed', () => () => <div><h2>Needs you</h2></div>);
jest.mock('../cards/NetWorthCard', () => () => <div><h2>Net Worth</h2></div>);
jest.mock('../cards/CashFlowCard', () => () => <div><h2>Cash Flow</h2></div>);
jest.mock('../cards/SpendingByCategoryCard', () => () => <div><h2>Spending by Category</h2></div>);
jest.mock('../cards/BudgetsCard', () => () => <div><h2>Budgets</h2></div>);
jest.mock('../cards/UpcomingBillsCard', () => () => <div><h2>Upcoming Bills</h2></div>);

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

// A household with a mortgage: the case the hero exists for, since the total
// is negative and the composition is what explains it.
const SUMMARY = {
  net_worth: -87399.21,
  total_cash: 65261.47,
  total_investments: 277341.07,
  total_real_assets: 0,
  total_credit_debt: 430001.75,
  accounts: [
    { id: 'a1', type: 'depository', subtype: 'checking', ledger: 65261.47 },
    { id: 'a2', type: 'investment', subtype: 'brokerage', ledger: 277341.07 },
    { id: 'c1', type: 'credit', subtype: 'credit_card', ledger: 10609.76 },
    { id: 'm1', type: 'credit', subtype: 'loan', ledger: 419391.99 },
  ],
};

const renderTab = ({
  comparison = spendComparison(),
  signals,
  summary = SUMMARY,
  ratios = { emergency_fund: { months_covered: 3.2, target_months: 6 } },
  creditHealth = { overall_utilization_pct: 19.7, cards_over_30: 1 },
} = {}) => {
  getDashboard.mockResolvedValue({
    data: {
      months: [], spending_by_month: {}, monthly_totals: [],
      net_worth_timeseries: [], recurring_charges: [],
      balance_trend: { available: false },
      spend_comparison: comparison,
    },
  });
  getCreditHealth.mockResolvedValue({ data: creditHealth });
  getBalancesSummary.mockResolvedValue({ data: summary });
  getAfterTaxNetWorth.mockResolvedValue({ data: { available: false } });
  getRatios.mockResolvedValue({ data: ratios });
  return render(
    <DashboardTab healthScore={70} healthSignals={signals} summary={summary} />,
  );
};

const hero = () => screen.getByRole('region', { name: /where you stand/i });

beforeEach(() => jest.clearAllMocks());

// The figure comes from the balances summary, which is the one place in the
// app that nets every account. `balance_trend` is computed from
// balance_snapshots and reports a different number on the same payload.
test('net worth is the summary figure, not the trend series', async () => {
  renderTab();

  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  expect(getBalancesSummary).not.toHaveBeenCalled();
});

// A negative net worth reads as a catastrophe until the composition shows a
// mortgage behind it, so the parts are drawn to scale and named.
test('the composition names every part of the position', async () => {
  renderTab();

  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  expect(hero()).toHaveTextContent(/Cash\s*\$65,261/);
  expect(hero()).toHaveTextContent(/Investments\s*\$277,341/);
  expect(hero()).toHaveTextContent(/Cards\s*\$10,610/);
  expect(hero()).toHaveTextContent(/Loans\s*\$419,392/);
  expect(screen.getByRole('img', { name: /what you own against what you owe/i }))
    .toBeInTheDocument();
});

test('a loan-dominated debt says what the position is without it', async () => {
  renderTab();

  await waitFor(() => expect(hero()).toHaveTextContent(/Loans are 98% of what you owe/i));
  expect(hero()).toHaveTextContent('$331,992.78');
});

// Nothing to explain when the debt is ordinary revolving balances.
test('a household with no loans gets no aside', async () => {
  renderTab({
    summary: {
      net_worth: 54651.71,
      total_cash: 65261.47,
      total_investments: 0,
      total_real_assets: 0,
      total_credit_debt: 10609.76,
      accounts: [
        { id: 'a1', type: 'depository', subtype: 'checking', ledger: 65261.47 },
        { id: 'c1', type: 'credit', subtype: 'credit_card', ledger: 10609.76 },
      ],
    },
  });

  await waitFor(() => expect(hero()).toHaveTextContent('$54,651.71'));
  expect(hero()).not.toHaveTextContent(/of what you owe/i);
});

test('the readings sit beside the figure rather than in four tiles', async () => {
  renderTab({ signals: undefined });

  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  expect(hero()).toHaveTextContent(/Health score\s*70/);
  expect(hero()).toHaveTextContent(/Runway\s*3\.2 mo/);
  expect(hero()).toHaveTextContent(/Utilization\s*19\.7%/);
  expect(hero()).toHaveTextContent(/1 card over 30%/);
});

test('income joins the readings when it has been detected', async () => {
  renderTab({
    ratios: {
      emergency_fund: { months_covered: 3.2, target_months: 6 },
      income: { monthly: 8238.32, source: 'detected' },
    },
  });

  await waitFor(() => expect(hero()).toHaveTextContent(/Income\s*\$8,238/));
  expect(hero()).toHaveTextContent(/detected monthly/i);
});

// The score is renormalized over whatever had data, so how much of the model
// was covered belongs next to the number.
const signalSet = (availableCount) => [
  'emergency_runway', 'savings_rate', 'credit_utilization',
  'debt_to_income', 'net_worth_trend',
].map((key, i) => ({
  key, label: key, weight: 20, detail: 'detail', available: i < availableCount,
}));

test('the score says how many signals it is based on', async () => {
  renderTab({ signals: signalSet(4) });

  await waitFor(() => expect(hero()).toHaveTextContent('4 of 5 signals'));
});

// The old "This Month" tile divided an empty month by a full one and reported
// a 100% drop every time a sync ran late, which is the most alarming possible
// way to say "no data yet".
test('a late sync is stated as a sync problem, not a spending drop', async () => {
  renderTab({
    comparison: spendComparison({
      as_of_day: 4,
      current_month: '2026-09',
      current_month_to_date: 0,
      prior_month: '2026-08',
      delta: -337.79,
      pct_change: -100.0,
    }),
  });

  const notice = await screen.findByRole('status');
  expect(notice).toHaveTextContent(/Nothing has synced since August/i);
  expect(notice).toHaveTextContent(/September is empty — not a drop in spending/i);
  expect(screen.queryByText(/100%/)).toBeNull();
});

test('a month with transactions in it raises no notice', async () => {
  renderTab();

  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  expect(screen.queryByRole('status')).toBeNull();
});

test('the first of the month is not a stale sync', async () => {
  renderTab({
    comparison: spendComparison({ as_of_day: 1, current_month_to_date: 0 }),
  });

  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  expect(screen.queryByRole('status')).toBeNull();
});

test('the grid renders exactly the six survivors', async () => {
  renderTab();
  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));

  expect(screen.getByRole('heading', { name: 'Net Worth' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Cash Flow' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Spending by Category' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Budgets' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Upcoming Bills' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Needs you' })).toBeInTheDocument();

  expect(screen.queryByText('Balances')).toBeNull();
  expect(screen.queryByText('Recurring Charges')).toBeNull();
  expect(screen.queryByText('Alerts')).toBeNull();
  expect(screen.queryByText(/weekly digest/i)).toBeNull();
  expect(screen.queryByText(/portfolio/i)).toBeNull();
  expect(screen.queryByText('Income vs. Expenses')).toBeNull();
});

test('the blur toggle has no emoji and stays text-only', async () => {
  renderTab();
  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));
  const toggle = screen.getByRole('button', { name: /hide numbers/i });
  expect(toggle.textContent).toBe('Hide numbers');
});

test('hiding numbers blurs the figure but keeps the page readable', async () => {
  renderTab();
  await waitFor(() => expect(hero()).toHaveTextContent('-$87,399.21'));

  await userEvent.setup().click(screen.getByRole('button', { name: /hide numbers/i }));

  expect(screen.getByText('-$87,399.21')).toHaveClass('eh-blur');
  expect(screen.getByRole('button', { name: /show numbers/i })).toBeInTheDocument();
});
