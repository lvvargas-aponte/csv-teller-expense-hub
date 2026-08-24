import React from 'react';
import { render, screen } from '@testing-library/react';
import FinancesSidebar, { resolveStoredTab } from '../FinancesSidebar';

jest.mock('axios');

const renderSidebar = () => render(
  <FinancesSidebar activeId="dashboard" onNavigate={jest.fn()} healthScore={70} />,
);

test('bills and subscriptions are one Commitments entry', () => {
  renderSidebar();

  expect(screen.getByRole('button', { name: 'Commitments' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Bills' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Subscriptions' })).toBeNull();
});

describe('the stored tab id survives the merge', () => {
  test('a returning user holding bills lands on Commitments', () => {
    expect(resolveStoredTab('bills')).toEqual({ tab: 'commitments', view: 'due' });
  });

  test('a returning user holding subscriptions lands on its Recurring view', () => {
    expect(resolveStoredTab('subscriptions')).toEqual({
      tab: 'commitments', view: 'recurring',
    });
  });

  test('any other stored id is left alone', () => {
    expect(resolveStoredTab('accounts')).toEqual({ tab: 'accounts', view: 'due' });
  });

  test('an empty store opens the dashboard', () => {
    expect(resolveStoredTab(null)).toEqual({ tab: 'dashboard', view: 'due' });
  });
});

test('Overview is retired — the dashboard is the landing view', () => {
  renderSidebar();

  expect(screen.queryByRole('button', { name: 'Overview' })).toBeNull();
  expect(resolveStoredTab('overview')).toEqual({ tab: 'dashboard', view: 'due' });
});
