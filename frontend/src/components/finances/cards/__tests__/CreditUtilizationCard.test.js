import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CreditUtilizationCard from '../CreditUtilizationCard';
import { getCreditHealth } from '../../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../../api/dashboard');

const health = (over = {}) => ({
  accounts: [{
    account_id: 'c1', institution: 'Chase', name: 'Sapphire',
    balance: 4200, credit_limit: 10000, utilization_pct: 42, status: 'warn',
  }],
  total_balance: 4200,
  total_limit: 10000,
  overall_utilization_pct: 42,
  overall_status: 'warn',
  carry_cost: {
    monthly_interest: 87.47, annual_interest: 1049.64,
    accounts_missing_apr: 0,
    by_account: [{
      account_id: 'c1', name: 'Sapphire', balance: 4200,
      apr: 24.99, monthly_interest: 87.47,
    }],
  },
  ...over,
});

const renderCard = (data, props = {}) => {
  getCreditHealth.mockResolvedValue({ data });
  return render(<CreditUtilizationCard {...props} />);
};

beforeEach(() => jest.clearAllMocks());

test('puts a monthly price on the balances', async () => {
  renderCard(health());

  expect(await screen.findByText(/costs about \$87\/month/i)).toBeInTheDocument();
});

test('cards with no APR are named as the reason the figure is short', async () => {
  const onNavigate = jest.fn();
  renderCard(
    health({
      carry_cost: {
        monthly_interest: 87.47, annual_interest: 1049.64,
        accounts_missing_apr: 2, by_account: [],
      },
    }),
    { onNavigate },
  );

  const link = await screen.findByRole('button', { name: /2 cards have no APR set/i });
  await userEvent.click(link);
  expect(onNavigate).toHaveBeenCalledWith('accounts');
});

test('no debt means no carry-cost headline', async () => {
  renderCard(health({
    carry_cost: {
      monthly_interest: 0, annual_interest: 0,
      accounts_missing_apr: 0, by_account: [],
    },
  }));

  await screen.findAllByText('42%');
  expect(screen.queryByText(/costs about/i)).toBeNull();
});

// Utilization is good/warn/high in colour alone; one reader in twelve cannot
// separate the red from the green, so the band gets its word.
test('utilization bands carry their word alongside the colour', async () => {
  renderCard(health({
    overall_status: 'high',
    overall_utilization_pct: 92,
    accounts: [{
      account_id: 'c1', institution: 'Chase', name: 'Sapphire',
      balance: 9200, credit_limit: 10000, utilization_pct: 92, status: 'high',
    }],
  }));

  expect(await screen.findAllByText('High')).toHaveLength(2);
});
