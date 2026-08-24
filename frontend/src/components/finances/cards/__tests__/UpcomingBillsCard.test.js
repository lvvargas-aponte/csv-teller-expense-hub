import React from 'react';
import { render, screen } from '@testing-library/react';
import UpcomingBillsCard from '../UpcomingBillsCard';
import { getUpcomingBills } from '../../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../../api/dashboard');

const payload = (over = {}) => ({
  today: '2026-08-24',
  window_days: 30,
  bills: [
    {
      account_id: 'c1', name: 'Everyday Card', institution: 'Bank',
      type: 'credit', due_day: 15, due_date: '2026-09-15', days_until: 22,
      balance: 2000, minimum_payment: 45, amount_due: 45,
    },
    {
      account_id: null, name: 'STATE FARM', institution: 'Insurance',
      type: 'recurring', due_day: 12, due_date: '2026-09-12', days_until: 19,
      balance: 140, minimum_payment: null, amount_due: 140,
      category: 'Insurance', merchant_key: 'state farm',
    },
  ],
  total_due: 185,
  total_due_by_kind: { credit: 45, recurring: 140 },
  ...over,
});

const renderCard = (data) => {
  getUpcomingBills.mockResolvedValue({ data });
  return render(<UpcomingBillsCard />);
};

beforeEach(() => jest.clearAllMocks());

test('leads with what is due in the window', async () => {
  renderCard(payload());

  expect(await screen.findByText('$185.00')).toBeInTheDocument();
  expect(screen.getByText(/due in the next 30 days/i)).toBeInTheDocument();
});

test('a card is listed for its minimum, with the balance as context', async () => {
  renderCard(payload());

  const row = await screen.findByText('Everyday Card');
  const amounts = screen.getAllByText('$45.00');
  expect(row).toBeInTheDocument();
  expect(amounts.length).toBeGreaterThan(0);
  expect(screen.getByText(/\$2,000\.00 balance/i)).toBeInTheDocument();
});

test('a card with no minimum set says so instead of showing nothing', async () => {
  renderCard(payload({
    bills: [{
      account_id: 'c1', name: 'Everyday Card', institution: 'Bank',
      type: 'credit', due_day: 15, due_date: '2026-09-15', days_until: 22,
      balance: 2000, minimum_payment: null, amount_due: null,
    }],
    total_due: 0,
    total_due_by_kind: { credit: 0, recurring: 0 },
  }));

  expect(await screen.findByText(/no minimum set/i)).toBeInTheDocument();
});
