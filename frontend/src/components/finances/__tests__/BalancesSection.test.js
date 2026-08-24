import React from 'react';
import { render, screen } from '@testing-library/react';
import BalancesSection from '../BalancesSection';

jest.mock('axios');

const card = (over = {}) => ({
  id: 'c1', institution: 'Bank', name: 'Everyday Card', type: 'credit',
  subtype: '', available: 0, ledger: 0, manual: false, ...over,
});

const renderSection = (accounts) => render(
  <BalancesSection
    summary={{
      accounts, net_worth: 0, total_cash: 0,
      total_credit_debt: 0, total_investments: 0,
    }}
    loading={false}
    error={null}
    onRefresh={jest.fn()}
    onMutate={jest.fn()}
  />,
);

test('a card you just paid off stays listed and is marked paid off', () => {
  renderSection([card({ ledger: 0 })]);

  expect(screen.getByText('Everyday Card')).toBeInTheDocument();
  expect(screen.getByText(/paid off/i)).toBeInTheDocument();
});

test('a card carrying a balance is not marked paid off', () => {
  renderSection([card({ ledger: 1200 })]);

  expect(screen.getByText('Everyday Card')).toBeInTheDocument();
  expect(screen.queryByText(/paid off/i)).toBeNull();
});
