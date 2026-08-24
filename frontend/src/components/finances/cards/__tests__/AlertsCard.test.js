import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AlertsCard from '../AlertsCard';
import { getAlerts } from '../../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../../api/dashboard');

const feed = (alerts) => ({
  alerts,
  counts: { error: 0, warn: alerts.length, info: 0 },
});

const renderCard = (alerts, props = {}) => {
  getAlerts.mockResolvedValue({ data: feed(alerts) });
  return render(<AlertsCard {...props} />);
};

beforeEach(() => jest.clearAllMocks());

test('an alert with a tab is actionable', async () => {
  const onNavigate = jest.fn();
  renderCard(
    [{ severity: 'warn', category: 'budget', message: 'Dining is pacing to $930', tab: 'budgets' }],
    { onNavigate },
  );

  const alert = await screen.findByRole('button', { name: /Dining is pacing to \$930/ });
  await userEvent.click(alert);

  expect(onNavigate).toHaveBeenCalledWith('budgets');
});

test('an alert with nowhere to go is still readable, just not clickable', async () => {
  renderCard([{ severity: 'info', category: 'recurring', message: 'Netflix went up', tab: null }]);

  expect(await screen.findByText(/Netflix went up/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Netflix went up/ })).toBeNull();
});
