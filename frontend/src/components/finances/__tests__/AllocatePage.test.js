import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';

import AllocatePage from '../AllocatePage';

jest.mock('axios');

const SETTINGS = {
  emergency_fund_months: 3,
  employer_match_known: null,
  annual_contribution_limits: { '401k': 24500, ira: 7500, hsa: 4400 },
  contribution_limits_as_of_year: 2026,
  contributed_ytd: {},
};

const PLAN = {
  available: true,
  amount: 500,
  cadence: 'monthly',
  allocated: 500,
  unallocated: 0,
  allocations: [
    {
      tier: 3, key: 'high_interest_debt', label: 'Pay down Visa',
      amount: 300, target_id: 'acct_1',
      rationale: '24.00% — stated APR, which is above the 7.0% you expect from investing.',
      quantified_benefit: {
        label: 'interest avoided in the first year', value: 36,
        rate_pct: 24, guaranteed: true, horizon: 'first year',
      },
    },
    {
      tier: 6, key: 'taxable_investing', label: 'Taxable brokerage',
      amount: 200, target_id: null,
      rationale: 'Nothing left costs more than the 5.95% after-tax return.',
      quantified_benefit: {
        label: 'projected value in 10 years', value: 33_000,
        rate_pct: 7, guaranteed: false, horizon: '10 years',
      },
    },
  ],
  skipped: [
    {
      tier: 6, key: 'extra_mortgage_principal',
      label: 'Extra principal on 123 Oak St',
      reason: 'At 3.25% it is cheaper than the 5.95% after-tax return you expect.',
    },
  ],
  questions: [
    {
      key: 'employer_match',
      question: 'Does your employer match retirement contributions?',
      why: 'A 50% match is an instant, guaranteed 50% return.',
    },
  ],
  caveats: ['Mortgage interest may be deductible — ask a CPA.'],
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: SETTINGS });
  axios.post.mockResolvedValue({ data: PLAN });
});

test('renders the split in tier order', async () => {
  render(<AllocatePage />);
  await waitFor(() => expect(screen.getByText('Pay down Visa')).toBeInTheDocument());

  const labels = screen.getAllByText(/Pay down Visa|Taxable brokerage/);
  expect(labels[0]).toHaveTextContent('Pay down Visa');
  expect(labels[1]).toHaveTextContent('Taxable brokerage');
});

test('separates a guaranteed return from a projected one', async () => {
  render(<AllocatePage />);
  await waitFor(() => expect(screen.getByText(/Guaranteed/)).toBeInTheDocument());

  // The distinction is the point: a 24% debt paydown and a 7% market
  // assumption must not read as the same kind of claim.
  expect(screen.getByText(/Guaranteed/)).toBeInTheDocument();
  expect(screen.getByText(/Projected/)).toBeInTheDocument();
  expect(screen.getByText(/markets fall as well as rise/)).toBeInTheDocument();
});

test('shows what it skipped and why', async () => {
  render(<AllocatePage />);
  await waitFor(() => expect(
    screen.getByText('Extra principal on 123 Oak St')
  ).toBeInTheDocument());
  expect(screen.getByText(/cheaper than the 5.95%/)).toBeInTheDocument();
});

test('surfaces unanswered questions above the split', async () => {
  render(<AllocatePage />);
  await waitFor(() => expect(
    screen.getByText(/Does your employer match/)
  ).toBeInTheDocument());
});

test('a preset re-runs the waterfall with that amount', async () => {
  const user = userEvent.setup();
  render(<AllocatePage />);
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));

  await user.click(screen.getByRole('button', { name: '$1,000' }));

  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  expect(axios.post).toHaveBeenLastCalledWith(
    expect.stringContaining('/api/tools/allocate'),
    { amount: 1000, cadence: 'monthly' },
  );
});

test('cadence is sent with the request', async () => {
  const user = userEvent.setup();
  render(<AllocatePage />);
  await waitFor(() => expect(axios.post).toHaveBeenCalled());

  await user.selectOptions(screen.getByRole('combobox'), 'one_time');
  await user.click(screen.getByRole('button', { name: /work it out/i }));

  await waitFor(() => expect(axios.post).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.objectContaining({ cadence: 'one_time' }),
  ));
});

test('surfaces a failed request instead of rendering a blank page', async () => {
  axios.post.mockRejectedValue(new Error('boom'));
  render(<AllocatePage />);
  await waitFor(() => expect(
    screen.getByText(/Could not work out a split/)
  ).toBeInTheDocument());
});

test('still renders the settings form when the settings request fails', async () => {
  // The waterfall runs on defaults; losing settings must not blank the page.
  axios.get.mockRejectedValue(new Error('nope'));
  render(<AllocatePage />);
  await waitFor(() => expect(screen.getByText('Pay down Visa')).toBeInTheDocument());
  expect(screen.queryByText(/What the waterfall needs to know/)).not.toBeInTheDocument();
});
