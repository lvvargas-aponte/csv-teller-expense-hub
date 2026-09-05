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

  expect(await screen.findByText(/~\$87\/month/i)).toBeInTheDocument();
});

test('cards with no APR are named as the reason the figure is short', async () => {
  renderCard(
    health({
      carry_cost: {
        monthly_interest: 87.47, annual_interest: 1049.64,
        accounts_missing_apr: 2, by_account: [],
      },
    }),
  );

  expect(await screen.findByText(/2 cards have no APR set/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /no APR set/i })).toBeNull();
});

test('no debt means no carry-cost figure', async () => {
  renderCard(health({
    carry_cost: {
      monthly_interest: 0, annual_interest: 0,
      accounts_missing_apr: 0, by_account: [],
    },
  }));

  await screen.findAllByText('42%');   // the headline figure and the row's
  expect(screen.queryByText(/\$87\/month/i)).toBeNull();
});

// Utilization is good/warn/high in colour alone; one reader in twelve cannot
// separate the red from the green. The band used to be spelled out beside each
// percentage; the shelves drawn into the track carry it now, so a bar's
// position against them is legible without colour — and the accessible name
// still says the band in words.
test('the band survives without colour', async () => {
  renderCard(health({
    overall_status: 'high',
    overall_utilization_pct: 92,
    accounts: [{
      account_id: 'c1', institution: 'Chase', name: 'Sapphire',
      balance: 9200, credit_limit: 10000, utilization_pct: 92, status: 'high',
    }],
  }));

  const bar = await screen.findByRole('progressbar', { name: /Sapphire utilization/i });
  expect(bar).toHaveAttribute('aria-valuetext', '92% used — High');
  expect(screen.getByText(/bars mark 10% and 30%/i)).toBeInTheDocument();
});

// `set limit →` was a bare span for as long as this card existed — the arrow
// read as a link and clicking it did nothing.
const NO_LIMIT = health({
  accounts: [{
    account_id: 'c2', institution: 'Amex', name: 'Gold',
    balance: 1240, credit_limit: null, utilization_pct: null, status: 'unknown',
  }],
});

test('a card with no limit offers a real control to set one', async () => {
  const onSetLimit = jest.fn();
  renderCard(NO_LIMIT, { onSetLimit });

  await userEvent.click(await screen.findByRole('button', { name: /set limit for Gold/i }));
  expect(onSetLimit).toHaveBeenCalledWith('c2');
});

// Nothing renders this card without a handler today, but a dead arrow is
// exactly the bug this replaced — so without somewhere to go, it says so.
test('with nowhere to send you, it states the fact instead of faking a link', async () => {
  renderCard(NO_LIMIT);

  expect(await screen.findByText('No limit')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /set limit/i })).toBeNull();
});

const GROWING = health({
  latest_month: '2026-08',
  cards_over_30: 1,
  to_30_total: 1200,
  to_10_total: 3200,
  interest_billed_latest: 36.51,
  accounts: [{
    account_id: 'c1', institution: 'Chase', name: 'Sapphire',
    balance: 4200, credit_limit: 10000, utilization_pct: 42, status: 'warn',
    headroom: 5800,
    levers: [{ gets_to_pct: 30, amount: 1200 }, { gets_to_pct: 10, amount: 3200 }],
    projection: {
      net_change: 1675.15, projected_pct: 58.8, crosses: 50, months_to_limit: 3,
    },
    activity: {
      name: 'Sapphire',
      latest: {
        month: '2026-08', spend: 1738.26, payments: 99.62, interest: 36.51,
        net_change: 1675.15,
        largest_purchase: { description: 'PRINCESS CRUISE RES', amount: 1075.98, date: '2026-08-28' },
      },
    },
  }],
});

// A gauge says where a card sits; the projected segment says which way it is
// moving, which is the part a bar alone cannot carry.
test('a growing card shows where it lands next month', async () => {
  renderCard(GROWING);

  expect(await screen.findByText(/\+\$1,675.15/)).toBeInTheDocument();
  expect(screen.getByText(/→ 58.8%/)).toBeInTheDocument();
  expect(screen.getByText(/faded segment is next month at this pace/i)).toBeInTheDocument();
});

// The gap between a payment and what it actually retired is invisible on a
// statement, and is why a small payment can leave the balance unmoved.
test('a card over the shelf gets the payment-versus-interest sentence', async () => {
  renderCard(GROWING);

  const say = await screen.findByText(/brings it under 30%/i);
  expect(say).toHaveTextContent('$1,200.00 brings it under 30%');
  expect(say).toHaveTextContent(
    /Of the \$99.62 you paid in August, \$36.51 was interest/i,
  );
});

test('the pay-down amount rides along with each card', async () => {
  renderCard(GROWING);

  expect(await screen.findByText(/\$1,200.00 → under 30%/)).toBeInTheDocument();
});

// The aggregate can read fine while one card sits well over the shelf, and
// both feed a score independently.
test('the overall figure names how many cards break the shelf', async () => {
  renderCard(GROWING);

  expect(await screen.findByText(/1 card over 30%/i)).toBeInTheDocument();
  expect(screen.getByText(/The average looks fine/i)).toBeInTheDocument();
});

test('billed interest is shown beside the modelled cost, not instead of it', async () => {
  renderCard(GROWING);

  expect(await screen.findByText(/Interest billed in August/i)).toBeInTheDocument();
  expect(screen.getByText('$36.51')).toBeInTheDocument();
  expect(screen.getByText(/~\$87\/month/i)).toBeInTheDocument();
});

// Nothing about a shrinking, well-under-shelf card is worth a sentence.
test('a card with nothing wrong gets no sentence and no chip', async () => {
  renderCard(health({
    latest_month: '2026-08',
    cards_over_30: 0,
    to_30_total: 0,
    to_10_total: 0,
    interest_billed_latest: 0,
    overall_utilization_pct: 5,
    overall_status: 'good',
    accounts: [{
      account_id: 'c1', institution: 'Chase', name: 'Sapphire',
      balance: 500, credit_limit: 10000, utilization_pct: 5, status: 'good',
      headroom: 9500, levers: [], projection: null,
      activity: {
        name: 'Sapphire',
        latest: {
          month: '2026-08', spend: 100, payments: 600, interest: 0,
          net_change: -500, largest_purchase: null,
        },
      },
    }],
  }));

  await screen.findAllByText('5%');
  expect(screen.queryByText(/over 30%/i)).toBeNull();
  expect(screen.queryByText(/brings it under/i)).toBeNull();
  expect(screen.queryByText(/faded segment/i)).toBeNull();
  // A month that reduced the balance still reports its direction.
  expect(screen.getByText(/−\$500.00/)).toBeInTheDocument();
});

// A cleared card is not idle — its unused limit is what holds the aggregate
// down, which is worth knowing before closing one.
test('an unused card names the headroom it contributes', async () => {
  renderCard(health({
    latest_month: '2026-08',
    cards_over_30: 0,
    overall_utilization_pct: 0,
    overall_status: 'good',
    accounts: [{
      account_id: 'c1', institution: 'Amex', name: 'EveryDay',
      balance: 0, credit_limit: 8500, utilization_pct: 0, status: 'good',
      headroom: 8500, levers: [], projection: null, activity: null,
    }],
  }));

  expect(await screen.findByText(/\$8,500.00 of headroom holding your overall down/i))
    .toBeInTheDocument();
});

// The payload predates these fields on a cached response, and a card that
// renders nothing at all is worse than one that renders only its bars.
test('a payload with no activity still renders the bars', async () => {
  renderCard(health());

  expect(await screen.findByRole('progressbar', { name: /Sapphire utilization/i }))
    .toBeInTheDocument();
  expect(screen.queryByText(/brings it under/i)).toBeNull();
});
