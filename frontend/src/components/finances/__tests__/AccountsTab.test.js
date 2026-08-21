import React from 'react';
import { render, screen, within } from '@testing-library/react';
import axios from 'axios';
import AccountsTab from '../AccountsTab';

jest.mock('axios');
jest.mock('../../ui/Spin', () => () => <span data-testid="spin" />);

// A 401(k) filed as a depository account is the case that used to break: the
// cash list took every depository row, while the second list on the same page
// pulled investment subtypes out into their own group — so this account was
// rendered twice, under two contradictory headings.
const summary = {
  net_worth: 30000,
  total_cash: 5000,
  total_credit_debt: 2000,
  total_investments: 27000,
  accounts: [
    { id: 'c1', name: 'Sapphire',      institution: 'Chase',    type: 'credit',     ledger: 2000, available: 8000 },
    { id: 'd1', name: 'Checking',      institution: 'Chase',    type: 'depository', available: 5000, ledger: 5000 },
    { id: 'i1', name: 'Fidelity 401k', institution: 'Fidelity', type: 'depository', subtype: '401k', available: 27000, ledger: 27000 },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: {} });
});

const renderTab = (props = {}) =>
  render(<AccountsTab summary={summary} summaryLoading={false} {...props} />);

test('lists each account exactly once', async () => {
  renderTab();
  expect(await screen.findByText('Checking')).toBeInTheDocument();
  expect(screen.getAllByText('Checking')).toHaveLength(1);
  expect(screen.getAllByText('Fidelity 401k')).toHaveLength(1);
  expect(screen.getAllByText('Sapphire')).toHaveLength(1);
});

test('shows one Cash & Savings heading, not two', async () => {
  renderTab();
  await screen.findByText('Checking');
  expect(screen.getAllByRole('heading', { name: /cash & savings/i })).toHaveLength(1);
});

test('files an investment-subtype depository account under Investments', async () => {
  renderTab();
  await screen.findByText('Fidelity 401k');

  const investments = screen.getByRole('heading', { name: /investments & retirement/i })
    .closest('.acct-cash-card');
  expect(within(investments).getByText('Fidelity 401k')).toBeInTheDocument();
  expect(within(investments).queryByText('Checking')).toBeNull();

  const cash = screen.getByRole('heading', { name: /cash & savings/i })
    .closest('.acct-cash-card');
  expect(within(cash).queryByText('Fidelity 401k')).toBeNull();
});

test('states no net worth of its own — that figure lives on its own page', async () => {
  renderTab({ onViewNetWorth: jest.fn() });
  await screen.findByText('Checking');
  // The rail used to headline cash − owed as "Net worth", which ignored both
  // investments and property equity while still subtracting mortgages.
  expect(screen.queryByText(/^net worth$/i)).toBeNull();
  expect(screen.getByRole('button', { name: /net worth/i })).toBeInTheDocument();
});

test('group totals come from the summary, so they match the Net Worth page', async () => {
  const { container } = renderTab();
  await screen.findByText('Checking');
  const totals = [...container.querySelectorAll('.acct-list-total')].map((n) => n.textContent);
  expect(totals).toEqual([
    '$2,000.00 owed', // total_credit_debt
    '$5,000.00',      // total_cash — not the sum of every depository row
    '$27,000.00',     // total_investments, including the 401k filed as depository
  ]);
});
