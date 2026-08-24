import React from 'react';
import { render, screen } from '@testing-library/react';
import BudgetsSection from '../BudgetsSection';
import { listBudgets } from '../../../api/budgets';

jest.mock('axios');
jest.mock('../../../api/budgets');
jest.mock('../../../hooks/useCategories', () => ({
  useCategories: () => ({ categories: ['Dining'], counts: {} }),
}));

const budget = (over = {}) => ({
  category: 'Dining',
  monthly_limit: 500,
  notes: '',
  current_month_spent: 300,
  percent_used: 60,
  over_budget: false,
  month_progress_pct: 32.3,
  projected_month_end: 930,
  pace_status: 'over_pace',
  projected_overage: 430,
  ...over,
});

const renderSection = (rows) => {
  listBudgets.mockResolvedValue({ data: rows });
  return render(<BudgetsSection />);
};

beforeEach(() => jest.clearAllMocks());

test('a category heading over its cap is called out in words, not colour alone', async () => {
  renderSection([budget()]);

  await screen.findByText(/over pace/i);
  expect(screen.getByText(/pacing to \$930/i)).toBeInTheDocument();
});

test('the bar marks how much of the month has elapsed', async () => {
  renderSection([budget()]);

  const marker = await screen.findByRole('img', { name: /32% of the month elapsed/i });
  expect(marker).toBeInTheDocument();
});

test('a budget tracking with the month carries no warning chip', async () => {
  renderSection([budget({
    current_month_spent: 160, percent_used: 32,
    projected_month_end: 496, pace_status: 'on_track', projected_overage: null,
  })]);

  await screen.findByText('32% used');
  expect(screen.queryByText(/over pace/i)).toBeNull();
  expect(screen.getByText(/pacing to \$496/i)).toBeInTheDocument();
});

test('an already-blown budget says so rather than reading as merely fast', async () => {
  renderSection([budget({
    current_month_spent: 600, percent_used: 120,
    over_budget: true, pace_status: 'over_budget',
  })]);

  await screen.findByText(/over budget/i);
  expect(screen.queryByText(/over pace/i)).toBeNull();
});
