import React from 'react';
import { render, screen, within } from '@testing-library/react';
import BorrowingPowerPanel from '../BorrowingPowerPanel';
import { getBorrowingPower } from '../../../api/dashboard';

jest.mock('axios');
jest.mock('../../../api/dashboard');

const payload = (over = {}) => ({
  dti: {
    pct: 32.1,
    monthly_debt_payments: 2648.0,
    monthly_income: 8238.32,
    income_source: 'detected',
    income_confidence: 'high',
    comfortable_pct: 15.0,
    ceiling_pct: 43.0,
    debts_missing_payment: [],
    payments: [
      { account_id: 'm1', name: 'Mortgage 3934', balance: 419391.99, amount: 3053.14, source: 'entered' },
      { account_id: 'c1', name: 'JetBlue Plus', balance: 7873.27, amount: 204.86, source: 'estimated' },
    ],
  },
  interest_history: {
    months: [
      { month: '2026-06', interest: 1.28 },
      { month: '2026-07', interest: 46.76 },
      { month: '2026-08', interest: 91.25 },
    ],
    total_paid: 139.29,
    latest: 91.25,
    average: 46.43,
    trend: 'rising',
    highest: 91.25,
  },
  carry_cost: { monthly_interest: 173.02, accounts_missing_apr: 0 },
  ...over,
});

const renderPanel = (data) => {
  getBorrowingPower.mockResolvedValue({ data });
  return render(<BorrowingPowerPanel />);
};

beforeEach(() => jest.clearAllMocks());

// The whole reason this panel replaced the five-factor one: a score is a model
// fit to a bureau file and this app sees roughly a third of its inputs.
test('never shows a score, a grade or an estimated range', async () => {
  renderPanel(payload());

  await screen.findByText(/We don't estimate a credit score/i);
  expect(screen.queryByText(/estimated score|your score is|score range|grade/i)).toBeNull();
});

test('debt-to-income shows the arithmetic behind the figure', async () => {
  renderPanel(payload());

  expect(await screen.findByText('32.1%')).toBeInTheDocument();
  // A ratio with no visible numerator is not worth trusting, and this one is
  // assembled from hand-entered minimums and a detected paycheque.
  expect(screen.getByText(/\$2,648.00 in monthly debt payments/i)).toBeInTheDocument();
  expect(screen.getByText(/\$8,238.32 monthly income/i)).toBeInTheDocument();
  expect(screen.getByText(/detected from your deposits/i)).toBeInTheDocument();
  expect(screen.getByText(/43% — the mortgage ceiling/i)).toBeInTheDocument();
});

// A derived minimum tracks the balance as it is paid down, which a typed
// figure cannot — but it must never be mistaken for a statement number.
test('an estimated payment is labelled, an entered one is not', async () => {
  renderPanel(payload());

  expect(await screen.findByText('$204.86')).toBeInTheDocument();
  expect(screen.getByText('$3,053.14')).toBeInTheDocument();
  // One tag, on the derived row only.
  expect(screen.getAllByText('estimated')).toHaveLength(1);
  const rows = screen.getAllByRole('listitem');
  const jetblue = rows.find((r) => r.textContent.includes('JetBlue Plus'));
  const mortgage = rows.find((r) => r.textContent.includes('Mortgage 3934'));
  expect(within(jetblue).getByText('estimated')).toBeInTheDocument();
  expect(within(mortgage).queryByText('estimated')).toBeNull();
});

// The bug this guards: a household whose mortgage carries no minimum payment
// sums to the four cards that do — $148 against a $419k loan — and reports a
// DTI in the single digits.
test('a debt with no minimum payment withholds the figure and names the account', async () => {
  renderPanel(payload({
    dti: {
      pct: 1.8,
      monthly_debt_payments: 148.0,
      monthly_income: 8238.32,
      income_source: 'detected',
      income_confidence: 'high',
      comfortable_pct: 15.0,
      ceiling_pct: 43.0,
      debts_missing_payment: [
        { account_id: 'm1', name: 'Mortgage 3934', balance: 419391.99 },
      ],
    },
  }));

  expect(await screen.findByText(/Can't show this yet/i)).toBeInTheDocument();
  expect(screen.getByText('Mortgage 3934')).toBeInTheDocument();
  expect(screen.getByText('$419,391.99 owed')).toBeInTheDocument();
  // The wrong number must not appear anywhere.
  expect(screen.queryByText('1.8%')).toBeNull();
});

test('no income means the panel says so rather than dividing by a guess', async () => {
  renderPanel(payload({
    dti: {
      pct: null, monthly_debt_payments: 148.0, monthly_income: null,
      comfortable_pct: 15.0, ceiling_pct: 43.0, debts_missing_payment: [],
    },
  }));

  expect(await screen.findByText(/Needs a monthly income figure/i)).toBeInTheDocument();
});

// What the issuers actually billed, not what an APR model projects — and the
// shape of it over time, which a single month's figure cannot carry.
test('interest paid reports the total, the average and the trend', async () => {
  renderPanel(payload());

  expect(await screen.findByText('$139.29')).toBeInTheDocument();
  expect(screen.getByText(/paid in interest since Jun/i)).toBeInTheDocument();
  expect(screen.getByText(/averaging \$46.43 a month and climbing/i)).toBeInTheDocument();
});

test('a rising month is called out against the average', async () => {
  renderPanel(payload());

  // Matched on the paragraph itself: a plain text query lands on the inner
  // <strong>, which holds only half the sentence.
  const note = await screen.findByText(
    (_content, el) => el?.tagName === 'P'
      && /most expensive month yet/i.test(el.textContent || ''),
  );
  expect(note).toHaveTextContent('Aug was your most expensive month yet');
  expect(note).toHaveTextContent('2× your average');
  // The modelled figure rides along, clearly marked as the projection.
  expect(note).toHaveTextContent('about $173/month if nothing changes');
});

// One series and eight readings, so every month keeps its value on screen
// rather than behind a hover — and each carries its own text for a reader.
test('every month is readable without colour or a hover', async () => {
  renderPanel(payload());

  await screen.findByText('$139.29');
  expect(screen.getByLabelText(/Interest billed by month/i)).toBeInTheDocument();
  expect(screen.getByText('Jun: $1.28 in interest')).toBeInTheDocument();
  expect(screen.getByText('Aug: $91.25 in interest')).toBeInTheDocument();
});

test('a steady stretch gets the plain description, not an alarm', async () => {
  renderPanel(payload({
    interest_history: {
      months: [
        { month: '2026-06', interest: 40.0 },
        { month: '2026-07', interest: 42.0 },
        { month: '2026-08', interest: 41.0 },
      ],
      total_paid: 123.0, latest: 41.0, average: 41.0,
      trend: 'steady', highest: 42.0,
    },
  }));

  expect(await screen.findByText(/what the issuers actually billed/i)).toBeInTheDocument();
  expect(screen.queryByText(/most expensive month yet/i)).toBeNull();
});

test('no interest history means no block', async () => {
  renderPanel(payload({
    interest_history: {
      months: [], total_paid: 0, latest: null,
      average: null, trend: null, highest: null,
    },
  }));

  await screen.findByText(/We don't estimate a credit score/i);
  expect(screen.queryByText(/What the debt has cost you/i)).toBeNull();
});

test('the education block carries the facts people get wrong', async () => {
  renderPanel(payload());

  expect(await screen.findByText(/Rate shopping is one inquiry, not six/i)).toBeInTheDocument();
  expect(screen.getByText(/A hard inquiry costs under 5 points/i)).toBeInTheDocument();
  expect(screen.getByText(/One 30-day late payment is the expensive mistake/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /annualcreditreport\.com/i }))
    .toHaveAttribute('href', 'https://www.annualcreditreport.com');
});
