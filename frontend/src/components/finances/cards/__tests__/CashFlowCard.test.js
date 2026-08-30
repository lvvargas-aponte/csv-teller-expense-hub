import React from 'react';
import { render, screen } from '@testing-library/react';
import CashFlowCard from '../CashFlowCard';
import { getCashflowProjection } from '../../../../api/cashflow';
import { getIncomeVsExpenses } from '../../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../../api/cashflow');
jest.mock('../../../../api/dashboard');

const projection = (over = {}) => ({
  horizon_days: 30,
  expected_income: 5000,
  expected_inbound_transfers: 0,
  expected_recurring_outflow: 1500,
  expected_discretionary_outflow: 1200,
  discretionary_basis: {
    method: 'median_of_complete_months', months: 3, monthly: 1200, confidence: 'high',
  },
  projection_incomplete: false,
  net: 2300,
  upcoming_bills: [],
  ...over,
});

const incomeVsExpenses = (over = {}) => ({
  rows: [
    { month: 'Jun', income: 5000, expenses: 3200, net: 1800 },
    { month: 'Jul', income: 5100, expenses: 3400, net: 1700 },
  ],
  ...over,
});

const dashboard = {
  monthly_totals: [
    { month: 'Jun', total: 3200 },
    { month: 'Jul', total: 3400 },
  ],
};

const renderCard = (props = {}) => render(
  <CashFlowCard dashboard={dashboard} loading={false} error={null} months={6} {...props} />,
);

beforeEach(() => {
  jest.clearAllMocks();
  getCashflowProjection.mockResolvedValue({ data: projection() });
  getIncomeVsExpenses.mockResolvedValue({ data: incomeVsExpenses() });
});

test('renders all three regions: actuals, outlook, and income vs. expenses', async () => {
  renderCard();

  expect(screen.getByRole('heading', { name: 'Monthly Spending' })).toBeInTheDocument();
  expect(screen.getByText(/\$3,400/)).toBeInTheDocument();

  expect(await screen.findByRole('heading', { name: '30-Day Outlook' })).toBeInTheDocument();
  expect(screen.getByText(/Money in/i)).toBeInTheDocument();
  expect(screen.getByText(/Projected net/i)).toBeInTheDocument();

  expect(await screen.findByRole('heading', { name: 'Income vs. Expenses' })).toBeInTheDocument();
  expect(screen.getAllByText(/Income/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Expenses/i).length).toBeGreaterThan(0);
});

test('a failed outlook fetch still renders the actuals and income vs. expenses', async () => {
  getCashflowProjection.mockRejectedValue(new Error('nope'));

  renderCard();

  expect(screen.getByRole('heading', { name: 'Monthly Spending' })).toBeInTheDocument();
  expect(screen.getByText(/\$3,400/)).toBeInTheDocument();

  expect(await screen.findByText(/Could not load the cash-flow outlook\./i)).toBeInTheDocument();

  expect(await screen.findByRole('heading', { name: 'Income vs. Expenses' })).toBeInTheDocument();
  expect(await screen.findByText(/\$5,100/)).toBeInTheDocument();
});

test('a failed income vs. expenses fetch still renders the actuals and outlook', async () => {
  getIncomeVsExpenses.mockRejectedValue(new Error('nope'));

  renderCard();

  expect(screen.getByRole('heading', { name: 'Monthly Spending' })).toBeInTheDocument();

  expect(await screen.findByRole('heading', { name: '30-Day Outlook' })).toBeInTheDocument();
  expect(await screen.findByText(/Projected net/i)).toBeInTheDocument();

  expect(await screen.findByText(/Could not load income vs\. expenses\./i)).toBeInTheDocument();
});

test('passes months through to the income vs. expenses fetch', async () => {
  renderCard({ months: 12 });

  await screen.findByRole('heading', { name: 'Income vs. Expenses' });

  expect(getIncomeVsExpenses).toHaveBeenCalledWith(12);
});

// ── Important 2: an actuals error must not wipe the other two sections ─────
test('a dashboard error still renders the outlook and income sections', async () => {
  renderCard({ error: 'Could not load dashboard data.' });

  expect(screen.getByText('Could not load dashboard data.')).toBeInTheDocument();
  expect(screen.queryByText(/\$3,400/)).toBeNull();

  expect(await screen.findByRole('heading', { name: '30-Day Outlook' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Income vs. Expenses' })).toBeInTheDocument();
});

test('an empty actuals window still renders the outlook and income sections', async () => {
  renderCard({ dashboard: { monthly_totals: [] } });

  expect(screen.getByText('No spending in this window.')).toBeInTheDocument();

  expect(await screen.findByRole('heading', { name: '30-Day Outlook' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Income vs. Expenses' })).toBeInTheDocument();
});

test('the badge is honest when the actuals failed to load', async () => {
  renderCard({ error: 'Could not load dashboard data.' });
  expect(screen.getByText('Unavailable')).toBeInTheDocument();
  expect(screen.queryByText('On track')).toBeNull();
  expect(screen.queryByText('High')).toBeNull();
});
