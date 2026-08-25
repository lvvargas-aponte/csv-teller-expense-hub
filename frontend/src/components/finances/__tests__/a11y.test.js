import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import { axe } from 'jest-axe';

import FinancesPage from '../FinancesPage';
import { getHealthScore, getRatios } from '../../../api/health';
import { getBalancesSummary } from '../../../api/balances';
import {
  getDashboard, getIncomeVsExpenses, getAlerts, getCreditHealth, getCreditFactors,
} from '../../../api/dashboard';
import { getAfterTaxNetWorth, getContributionHeadroom } from '../../../api/tax';
import { getCashflowProjection } from '../../../api/cashflow';
import {
  getPortfolio, getPortfolioQuality, getPortfolioFees, getMixBacktest,
} from '../../../api/investments';
import { getLatestDigest, markDigestRead } from '../../../api/digest';
import { getAllAccountDetails } from '../../../api/accountDetails';
import { getSnapTradeConfig, listSnapTradeConnections } from '../../../api/snaptrade';
import { getProjection } from '../../../api/retirement';

jest.mock('axios');
jest.mock('../../../api/health');
jest.mock('../../../api/balances');
jest.mock('../../../api/dashboard');
jest.mock('../../../api/tax');
jest.mock('../../../api/cashflow');
jest.mock('../../../api/investments');
jest.mock('../../../api/digest');
jest.mock('../../../api/accountDetails');
jest.mock('../../../api/snaptrade');
jest.mock('../../../api/retirement');
jest.mock('../../../api/profile');

// ── AXE BASELINE ────────────────────────────────────────────────────
// Recorded at F1 over the whole Finances shell (sidebar + main + the
// dashboard, accounts and investments surfaces), with every card's fetch
// mocked so axe runs on settled content rather than loading spinners.
//
// This list is Workstream F's work queue. F2–F4 shrink it; it must be
// empty when F4 lands, and anything that survives stays here with the
// reason it could not be fixed in scope.
//
//   dashboard    violations: landmark-unique x1, region x27
//                needs review: aria-prohibited-attr x7
//   accounts     violations: empty-table-header x2, landmark-unique x1,
//                            region x13
//                needs review: aria-prohibited-attr x1
//   investments  violations: landmark-unique x1, region x20
//                needs review: aria-prohibited-attr x1
//
// After F2 (hover tooltips replaced by InfoPopover):
//   dashboard    violations: landmark-unique x1, region x29
//   accounts     violations: empty-table-header x2, landmark-unique x1,
//                            region x13
//   investments  violations: landmark-unique x1, region x20
//   aria-prohibited-attr is gone from all three.
//
// After F3 (colour paired with text): unchanged except region, which counts
// nodes and so grows with the words F3 added — dashboard region x37. Nothing
// F3 touched was axe-detectable; the contrast work it did is invisible to
// axe in jsdom and was verified by computing the ratios by hand.
//
// After F4 (landmarks, heading order, table semantics, nav state):
//   dashboard    violations: none      needs review: none
//   accounts     violations: none      needs review: none
//   investments  violations: none      needs review: none
// The queue is empty. Nothing survived that had to be carried forward.
//
// What each one was:
//   region               — .eh-main is a plain div, so nothing on the page
//                          sits inside a landmark.
//   landmark-unique      — FinancesSidebar emits one <nav> per section with
//                          no distinguishing name, so all three collide.
//   empty-table-header   — PayoffForm's checkbox and remove columns are
//                          <th></th>; no data table names itself either.
//   aria-prohibited-attr — the .eh-info-wrap tooltip triggers are bare
//                          <span tabIndex={0} aria-label="About …"> with no
//                          role, so the accessible name is prohibited and
//                          the widget is unreachable by keyboard.
//
// Two items on this workstream's queue are real but invisible to axe in
// jsdom, so they carry no count here: heading order (the topbar title is a
// styled div, so a card's h3 is the first heading on the page) and colour
// contrast (axe cannot measure it without layout — F3 checks the hexes by
// hand).
// ────────────────────────────────────────────────────────────────────

const summary = {
  net_worth: 588000,
  total_cash: 18000,
  total_investments: 430000,
  total_real_assets: 450000,
  total_credit_debt: 310000,
  cache_fetched_at: '2026-08-20T10:00:00',
  connections: [],
  accounts: [
    {
      id: 'c1', institution: 'Chase', name: 'Sapphire', type: 'credit',
      available: 400, ledger: -4600, source: 'simplefin', manual: false,
    },
    {
      id: 'd1', institution: 'Ally', name: 'Savings', type: 'depository',
      subtype: 'savings', available: 18000, ledger: 18000, source: 'simplefin', manual: false,
    },
    {
      id: 'r1', institution: 'Manual', name: 'Home', type: 'real_asset',
      subtype: 'home', available: 450000, ledger: 450000, source: 'manual', manual: true,
    },
  ],
};

const portfolio = {
  total_value: 430000,
  total_cost: 442400,
  total_gain: -12400,
  total_gain_pct: -2.8,
  holding_count: 2,
  allocation: [
    { asset_type: 'stock', value: 200000, pct: 46 },
    { asset_type: 'etf', value: 230000, pct: 54 },
  ],
  concentration: [
    { symbol: 'AAPL', value: 200000, pct: 46 },
    { symbol: 'VTI', value: 230000, pct: 54 },
  ],
  by_account: [],
  holdings: [
    {
      account_id: 'a1', account_name: 'Brokerage', institution: 'Fidelity',
      symbol: 'AAPL', description: 'Apple Inc.', asset_type: 'stock', quantity: 1000,
      average_purchase_price: 210, last_price: 200, market_value: 200000,
      cost_basis: 210000, unrealized_gain: -10000, gain_pct: -4.8,
    },
    {
      account_id: 'a1', account_name: 'Brokerage', institution: 'Fidelity',
      symbol: 'VTI', description: 'Vanguard Total Market', asset_type: 'etf', quantity: 1000,
      average_purchase_price: 232.4, last_price: 230, market_value: 230000,
      cost_basis: 232400, unrealized_gain: -2400, gain_pct: -1,
    },
  ],
};

function mockApis() {
  getHealthScore.mockResolvedValue({
    data: {
      score: 68,
      signals: [
        { key: 'emergency_runway', label: 'Emergency runway', weight: 25, detail: '1.4 months', available: true },
        { key: 'savings_rate', label: 'Savings rate', weight: 25, detail: '8%', available: true },
        { key: 'credit_utilization', label: 'Credit utilization', weight: 20, detail: '62%', available: true },
        { key: 'debt_to_income', label: 'Debt-to-income', weight: 15, detail: '38%', available: true },
        { key: 'net_worth_trend', label: 'Net worth trend', weight: 15, detail: 'no history', available: false },
      ],
    },
  });
  getBalancesSummary.mockResolvedValue({ data: summary });
  getRatios.mockResolvedValue({
    data: {
      emergency_fund: { months_covered: 1.4, target_months: 6, gap: 12000, cash: 18000 },
      income: { monthly: 5000, source: 'profile', detected_monthly: 4800 },
      savings_rate_pct: 8,
      monthly_expenses: 4600,
      dti_pct: 38,
      monthly_debt_payments: 1900,
    },
  });
  getDashboard.mockResolvedValue({
    data: {
      months: ['2026-06', '2026-07', '2026-08'],
      spending_by_month: { '2026-08': [{ category: 'dining', total: 220 }] },
      monthly_totals: [{ month: '2026-08', total: 1200 }],
      net_worth_timeseries: [{ date: '2026-08-01', net_worth: 580000 }],
      recurring_charges: [
        { description: 'Netflix', amount: 15.99, cadence: 'monthly', last_seen: '2026-08-02' },
      ],
      balance_trend: { available: true, current_net_worth: 588000, delta_30d: -1200 },
      spend_comparison: {
        as_of_day: 10,
        current_month: '2026-08',
        current_month_to_date: 120,
        prior_month: '2026-07',
        prior_month_same_period: 100,
        prior_month_full: 500,
        delta: 20,
        pct_change: 20,
        current_month_is_partial: true,
      },
    },
  });
  getIncomeVsExpenses.mockResolvedValue({
    data: {
      months: ['2026-06', '2026-07'],
      rows: [
        { month: '2026-06', income: 800, expenses: 300, net: 500, is_partial: false },
        { month: '2026-07', income: 1000, expenses: 1400, net: -400, is_partial: false },
      ],
    },
  });
  getAlerts.mockResolvedValue({
    data: {
      alerts: [
        { severity: 'error', message: 'Chase Sapphire is over 90% utilized.', tab: 'accounts' },
        { severity: 'warn', message: 'Dining is $120 over budget.', tab: 'budgets' },
        { severity: 'info', message: 'You saved $300 more than last month.' },
      ],
    },
  });
  getCreditHealth.mockResolvedValue({
    data: {
      overall_utilization_pct: 62,
      overall_status: 'warn',
      total_balance: 6200,
      total_limit: 10000,
      carry_cost: { monthly_interest: 88, annual_interest: 1056, accounts_missing_apr: 1 },
      accounts: [
        { account_id: 'a1', name: 'Sapphire', utilization_pct: 92, status: 'high', balance: 4600, credit_limit: 5000 },
        { account_id: 'a2', name: 'Freedom', utilization_pct: 32, status: 'good', balance: 1600, credit_limit: 5000 },
      ],
    },
  });
  getCreditFactors.mockResolvedValue({ data: { available: false, factors: [] } });
  getAfterTaxNetWorth.mockResolvedValue({ data: { available: false } });
  getContributionHeadroom.mockResolvedValue({ data: { available: false } });
  getCashflowProjection.mockResolvedValue({
    data: {
      horizon_days: 30,
      expected_income: 4000,
      expected_inbound_transfers: 0,
      expected_recurring_outflow: 2600,
      expected_discretionary_outflow: 1740,
      net: -340,
      discretionary_basis: { confidence: 'low' },
      projection_incomplete: false,
    },
  });
  getPortfolio.mockResolvedValue({ data: portfolio });
  getPortfolioQuality.mockResolvedValue({ data: { available: false } });
  getPortfolioFees.mockResolvedValue({ data: { available: false } });
  getMixBacktest.mockResolvedValue({ data: { available: false } });
  getSnapTradeConfig.mockResolvedValue({ data: { configured: true, connected: true } });
  listSnapTradeConnections.mockResolvedValue({ data: { connections: [] } });
  getProjection.mockResolvedValue({ data: { available: false } });
  getLatestDigest.mockResolvedValue({
    data: {
      id: 1,
      read: false,
      payload: {
        week_start: '2026-08-10',
        week_end: '2026-08-16',
        narrative: 'You spent $420 this week, $60 less than the week before.',
        spending: { this_week: 420, prior_week: 480, change_pct: -12 },
        subscriptions: { needs_review_count: 2, price_increases: [{ name: 'Spotify' }] },
        alert_counts: { error: 1, warn: 2, info: 3 },
        upcoming_bills: [{ description: 'Rent', amount: 1800, due_date: '2026-08-30' }],
      },
    },
  });
  markDigestRead.mockResolvedValue({ data: {} });
  getAllAccountDetails.mockResolvedValue({ data: {} });

  axios.get.mockImplementation((url) => {
    if (url.includes('/api/budgets')) {
      return Promise.resolve({
        data: [
          { category: 'dining', percent_used: 130, over_budget: true, spent: 520, limit: 400 },
          { category: 'groceries', percent_used: 94, over_budget: false, spent: 470, limit: 500 },
        ],
      });
    }
    if (url.includes('/api/categories')) {
      return Promise.resolve({ data: { categories: ['dining'], counts: { dining: 4 } } });
    }
    if (url.includes('/api/accounts/metadata')) {
      return Promise.resolve({ data: { investment_subtypes: ['brokerage'] } });
    }
    return Promise.resolve({ data: [] });
  });
  axios.put.mockResolvedValue({ data: {} });
}

async function renderTab(tab) {
  localStorage.setItem('finances.activeTab', tab);
  const { container } = render(
    <MemoryRouter><FinancesPage /></MemoryRouter>,
  );
  // Every card fetches for itself; axe has to run on settled content, not on
  // a grid of loading spinners.
  await waitFor(() => expect(screen.queryAllByText(/Loading/)).toHaveLength(0));
  return container;
}

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
  mockApis();
});

test('the dashboard has no axe violations', async () => {
  await renderTab('dashboard');
  expect(await axe(document.body)).toHaveNoViolations();
});

test('the accounts surface has no axe violations', async () => {
  await renderTab('accounts');
  expect(await axe(document.body)).toHaveNoViolations();
});

test('the investments surface has no axe violations', async () => {
  await renderTab('investments');
  expect(await axe(document.body)).toHaveNoViolations();
});

// Landmarks, a skip link and an announcement for content that swaps under
// the reader's feet — the three things a keyboard-only user needs before the
// page is navigable at all.
test('the shell has a main landmark reachable by a skip link', async () => {
  await renderTab('dashboard');

  const main = screen.getByRole('main');
  const skip = screen.getByRole('link', { name: /skip to main content/i });
  expect(skip).toHaveAttribute('href', `#${main.id}`);
});

test('a balance refresh is announced politely', async () => {
  await renderTab('accounts');

  const live = screen.getByRole('status');
  expect(live).toHaveAttribute('aria-live', 'polite');
  await waitFor(() => expect(live).toHaveTextContent(/balances updated/i));
});
