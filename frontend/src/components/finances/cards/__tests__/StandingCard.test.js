import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StandingCard from '../StandingCard';
import { getRatios } from '../../../../api/health';

jest.mock('axios');
jest.mock('../../../../api/health');

const ratios = (over = {}) => ({
  income: {
    monthly: 8000, source: 'profile', confidence: 'high',
    detected_monthly: 7100, profile_monthly: 8000,
  },
  savings_rate_pct: 25.0,
  monthly_expenses: 6000,
  emergency_fund: {
    cash: 14000, months_covered: 2.3, target_months: 6, gap: 22000,
  },
  monthly_debt_payments: 600,
  dti_pct: 7.5,
  as_of: '2026-08-24',
  ...over,
});

const renderCard = (data, props = {}) => {
  getRatios.mockResolvedValue({ data });
  return render(<StandingCard {...props} />);
};

const stat = (label) => screen.getByRole('group', { name: label });

beforeEach(() => jest.clearAllMocks());

test('reads the runway against its target', async () => {
  renderCard(ratios());

  await waitFor(() => expect(stat('Emergency runway')).toHaveTextContent('2.3 months'));
  expect(stat('Emergency runway')).toHaveTextContent(/3\.7 short of your 6-month target/);
  expect(stat('Emergency runway')).toHaveTextContent('$22,000.00');
});

test('shows the savings rate and what it is measured against', async () => {
  renderCard(ratios());

  await waitFor(() => expect(stat('Savings rate')).toHaveTextContent('25%'));
  expect(stat('Savings rate')).toHaveTextContent('$2,000.00');
  expect(stat('Debt-to-income')).toHaveTextContent('7.5%');
  expect(stat('Debt-to-income')).toHaveTextContent('$600.00');
});

test('a met target reads as met rather than as a negative shortfall', async () => {
  renderCard(ratios({
    emergency_fund: { cash: 40000, months_covered: 6.7, target_months: 6, gap: 0 },
  }));

  await waitFor(() => expect(stat('Emergency runway')).toHaveTextContent('6.7 months'));
  expect(stat('Emergency runway')).toHaveTextContent(/covers your 6-month target/i);
  expect(stat('Emergency runway')).not.toHaveTextContent('short');
});

test('a detected income figure is labelled as detected', async () => {
  renderCard(ratios({
    income: {
      monthly: 7100, source: 'detected', confidence: 'low',
      detected_monthly: 7100, profile_monthly: null,
    },
  }));

  await waitFor(() => expect(stat('Savings rate')).toHaveTextContent(/detected/i));
});

test('a missing ratio says what is missing and opens the settings pane', async () => {
  const user = userEvent.setup();
  const onOpenSettings = jest.fn();
  renderCard(
    ratios({
      income: {
        monthly: null, source: 'none', confidence: 'none',
        detected_monthly: null, profile_monthly: null,
      },
      savings_rate_pct: null,
      dti_pct: null,
    }),
    { onOpenSettings },
  );

  await waitFor(() => expect(stat('Savings rate')).toHaveTextContent(/income/i));
  expect(stat('Savings rate')).not.toHaveTextContent('25%');

  await user.click(screen.getAllByRole('button', { name: /add your income/i })[0]);
  expect(onOpenSettings).toHaveBeenCalledWith('profile');
});

test('no complete month of spending is stated rather than shown as zero', async () => {
  renderCard(ratios({
    monthly_expenses: null,
    savings_rate_pct: null,
    emergency_fund: { cash: 14000, months_covered: null, target_months: 3, gap: null },
  }));

  await waitFor(() => {
    expect(stat('Emergency runway')).toHaveTextContent(/no complete month of spending/i);
  });
  expect(stat('Emergency runway')).not.toHaveTextContent('0 months');
});
