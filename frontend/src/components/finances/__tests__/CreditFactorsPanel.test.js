import React from 'react';
import { render, screen } from '@testing-library/react';
import CreditFactorsPanel from '../CreditFactorsPanel';
import { getCreditFactors } from '../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../api/dashboard');

const factors = (over = {}) => ({
  utilization: {
    overall_reported_pct: 41.2,
    overall_current_pct: 22.8,
    cards: [{
      account_id: 'c1', name: 'Sapphire', reported_pct: 52.0, current_pct: 31.0,
      statement_day: 14, limit: 8000, reported_balance: 4160,
      as_of: '2026-08-14',
      lever: { pay_by: '2026-09-14', amount: 1760, gets_to_pct: 30 },
    }],
    cards_over_30: 1,
    all_cards_at_zero: false,
  },
  payment_timeliness: {
    cycles_observed: 14, cycles_with_payment_before_due: 14, latest: [],
  },
  history: {
    average_age_months: 74, oldest_account_months: 141,
    accounts_missing_opened_on: 3,
  },
  new_credit: { opened_last_12_months: 1 },
  mix: { revolving: 4, installment: 1 },
  coverage_note: 'Measured on 5 connected accounts.',
  ...over,
});

const renderPanel = (data) => {
  getCreditFactors.mockResolvedValue({ data });
  return render(<CreditFactorsPanel />);
};

beforeEach(() => jest.clearAllMocks());

test('never shows a score, a grade or an estimated range', async () => {
  renderPanel(factors());

  await screen.findByText(/We don't estimate a score/i);
  expect(screen.getByText(/annualcreditreport\.com/i)).toBeInTheDocument();
  expect(screen.queryByText(/estimated score|your score is|score range|grade/i)).toBeNull();
});

test('leads with the gap between reported and current utilization', async () => {
  renderPanel(factors());

  const util = await screen.findByRole('group', { name: /credit utilization/i });
  expect(util).toHaveTextContent('41.2%');
  expect(util).toHaveTextContent('22.8%');
  expect(util).toHaveTextContent(/statement/i);
});

test('a card over the threshold names the payment and the deadline', async () => {
  renderPanel(factors());

  expect(await screen.findByText(/Pay \$1,760\.00 by Sep 14, 2026/i)).toBeInTheDocument();
  expect(screen.getByText(/to report 30%/i)).toBeInTheDocument();
});

test('timeliness is phrased as what was observed, not as a clean record', async () => {
  renderPanel(factors());

  const timeliness = await screen.findByRole('group', { name: /payment history/i });
  expect(timeliness).toHaveTextContent(
    /14 of 14 observed cycles paid before the due date on your connected accounts/i,
  );
  expect(timeliness).not.toHaveTextContent(/no late payments/i);
});

test('missing open dates are asked for rather than averaged over silently', async () => {
  renderPanel(factors());

  const history = await screen.findByRole('group', { name: /length of history/i });
  expect(history).toHaveTextContent(/3 accounts have no open date/i);
});

test('a card with no statement snapshot says so instead of showing today', async () => {
  renderPanel(factors({
    utilization: {
      overall_reported_pct: null, overall_current_pct: 31.0,
      cards: [{
        account_id: 'c1', name: 'Sapphire', reported_pct: null, current_pct: 31.0,
        statement_day: 14, limit: 8000, reported_balance: null, as_of: null,
        lever: null,
      }],
      cards_over_30: 0, all_cards_at_zero: false,
    },
  }));

  const util = await screen.findByRole('group', { name: /credit utilization/i });
  expect(util).toHaveTextContent(/no statement-date balance recorded yet/i);
});
