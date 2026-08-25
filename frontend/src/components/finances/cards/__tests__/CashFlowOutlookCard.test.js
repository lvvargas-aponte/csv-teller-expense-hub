import React from 'react';
import { render, screen } from '@testing-library/react';
import CashFlowOutlookCard from '../CashFlowOutlookCard';
import { getCashflowProjection } from '../../../../api/cashflow';

jest.mock('axios');
jest.mock('../../../../api/cashflow');

const projection = (over = {}) => ({
  horizon_days: 30,
  expected_income: 5000,
  expected_inbound_transfers: 0,
  expected_recurring_outflow: 1500,
  expected_discretionary_outflow: 1200,
  discretionary_basis: {
    method: 'median_of_complete_months', months: 3, monthly: 1200, confidence: 'high',
  },
  projection_incomplete: false,
  net: 2300,
  upcoming_bills: [],
  ...over,
});

const renderCard = (over) => {
  getCashflowProjection.mockResolvedValue({ data: projection(over) });
  return render(<CashFlowOutlookCard />);
};

beforeEach(() => jest.clearAllMocks());

test('shows every component of the waterfall, not just the net', async () => {
  renderCard();

  expect(await screen.findByText(/\$5,000/)).toBeInTheDocument();
  expect(screen.getByText(/\$1,500/)).toBeInTheDocument();
  expect(screen.getByText(/\$1,200/)).toBeInTheDocument();
  expect(screen.getByText(/\$2,300/)).toBeInTheDocument();
  expect(screen.getByText(/Money in/i)).toBeInTheDocument();
  expect(screen.getByText(/Recurring bills/i)).toBeInTheDocument();
  expect(screen.getByText(/Typical spending/i)).toBeInTheDocument();
  expect(screen.getByText(/Projected net/i)).toBeInTheDocument();
});

test('labels the estimate as an estimate', async () => {
  renderCard();

  expect(await screen.findByText(/estimate/i)).toBeInTheDocument();
});

test('two months of history is labelled rough, never hidden', async () => {
  renderCard({
    expected_discretionary_outflow: 900,
    discretionary_basis: {
      method: 'median_of_complete_months', months: 2, monthly: 900, confidence: 'low',
    },
    net: 2600,
  });

  expect(await screen.findByText(/rough — two months of history/i)).toBeInTheDocument();
});

test('no usable history shows the recurring-only view and says so', async () => {
  renderCard({
    expected_discretionary_outflow: 0,
    discretionary_basis: {
      method: 'median_of_complete_months', months: 1, monthly: null, confidence: 'none',
    },
    projection_incomplete: true,
    net: 3500,
  });

  expect(await screen.findByText(/projection is incomplete/i)).toBeInTheDocument();
  expect(screen.queryByText('Typical spending')).toBeNull();
});

test('a negative net is stated in the same hedged words as the alert', async () => {
  renderCard({
    expected_income: 2000, expected_recurring_outflow: 1500,
    expected_discretionary_outflow: 840,
    discretionary_basis: {
      method: 'median_of_complete_months', months: 3, monthly: 840, confidence: 'high',
    },
    net: -340,
  });

  expect(
    await screen.findByText(/projected to exceed income by about \$340 over the next 30 days/i)
  ).toBeInTheDocument();
});
