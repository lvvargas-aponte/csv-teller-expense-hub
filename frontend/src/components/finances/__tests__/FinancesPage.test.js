import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';

import FinancesPage from '../FinancesPage';
import { getBalancesSummary } from '../../../api/balances';

jest.mock('axios');
jest.mock('../../../api/balances');

// Balances-consuming sections keep their real subtree elsewhere; here we
// only care whether FinancesPage's own effect fires getBalancesSummary, so
// every section subtree is stubbed to avoid dragging in their own fetches.
jest.mock('../DashboardTab', () => () => <div>dashboard</div>);
jest.mock('../AccountsTab', () => () => <div>accounts</div>);
jest.mock('../DebtPage', () => () => <div>debt</div>);
jest.mock('../InvestmentsTab', () => () => <div>invest</div>);
jest.mock('../BudgetsSection', () => () => <div>budgets</div>);
jest.mock('../GoalsSection', () => () => <div>goals</div>);
jest.mock('../AdvisorChat', () => () => <div>chat</div>);
jest.mock('../KnowledgeSection', () => () => <div>memory</div>);
jest.mock('../SubscriptionsSection', () => () => <div>subscriptions</div>);
jest.mock('../../settings/SettingsPage', () => () => <div>settings</div>);
jest.mock('../cards/RecurringChargesCard', () => () => <div>recurring</div>);
jest.mock('../cards/UpcomingBillsCard', () => () => <div>bills</div>);

function renderSection(section, view, subView) {
  return render(
    <MemoryRouter>
      <FinancesPage section={section} view={view} subView={subView} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  getBalancesSummary.mockResolvedValue({ data: {} });
  axios.get.mockResolvedValue({ data: {} });
  axios.delete.mockResolvedValue({ data: {} });
});

test('home fetches balances', async () => {
  renderSection('home');
  await waitFor(() => expect(getBalancesSummary).toHaveBeenCalledTimes(1));
});

test('accounts fetches balances', async () => {
  renderSection('accounts');
  await waitFor(() => expect(getBalancesSummary).toHaveBeenCalledTimes(1));
});

test('debt fetches balances', async () => {
  renderSection('debt');
  await waitFor(() => expect(getBalancesSummary).toHaveBeenCalledTimes(1));
});

test('invest fetches balances', async () => {
  renderSection('invest');
  await waitFor(() => expect(getBalancesSummary).toHaveBeenCalledTimes(1));
});

test('plan does not fetch balances', async () => {
  renderSection('plan', 'budgets');
  await screen.findByText('budgets');
  expect(getBalancesSummary).not.toHaveBeenCalled();
});

test('ask does not fetch balances', async () => {
  renderSection('ask', 'chat');
  await screen.findByText('chat');
  expect(getBalancesSummary).not.toHaveBeenCalled();
});

test('settings does not fetch balances', async () => {
  renderSection('settings');
  await screen.findByText('settings');
  expect(getBalancesSummary).not.toHaveBeenCalled();
});
