import React from 'react';
import { render, screen } from '@testing-library/react';

import SafeToSpendCard from '../SafeToSpendCard';

const payload = (overrides = {}) => ({
  available: true,
  daily_safe_to_spend: 84.12,
  weekly_safe_to_spend: 588.84,
  remaining_pool: 1430,
  over_budget: false,
  overspend_amount: 0,
  pace: 'on_track',
  period: { days_remaining: 17, days_total: 31, days_elapsed: 15 },
  ...overrides,
});

test('renders the daily figure', () => {
  render(<SafeToSpendCard data={payload()} />);
  expect(screen.getByText('$84.12')).toBeInTheDocument();
});

test('renders the weekly figure and days remaining', () => {
  render(<SafeToSpendCard data={payload()} />);
  expect(screen.getByText(/\$588\.84 for the next/)).toBeInTheDocument();
  expect(screen.getByText(/17 days left/)).toBeInTheDocument();
});

test('caps the weekly window when fewer than seven days remain', () => {
  render(<SafeToSpendCard data={payload({ period: { days_remaining: 3 } })} />);
  expect(screen.getByText(/for the next\s*3 days/)).toBeInTheDocument();
});

test('shows nothing at all when the data is missing', () => {
  const { container } = render(<SafeToSpendCard data={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('explains itself rather than showing a number when income is unknown', () => {
  render(<SafeToSpendCard data={{
    available: false,
    detail: 'No recurring income found in your transactions.',
  }} />);
  expect(screen.getByText('Not enough to go on yet')).toBeInTheDocument();
  expect(screen.getByText(/No recurring income found/)).toBeInTheDocument();
});

test('over budget replaces the pace line with the shortfall', () => {
  render(<SafeToSpendCard data={payload({
    over_budget: true, overspend_amount: 340, daily_safe_to_spend: 0,
  })} />);
  expect(screen.getByText(/\$340\.00 past the month/)).toBeInTheDocument();
  expect(screen.queryByText(/Tracking with the month/)).toBeNull();
});

test('shows the change against yesterday', () => {
  render(
    <SafeToSpendCard
      data={payload({ daily_safe_to_spend: 84.12 })}
      yesterday={payload({ daily_safe_to_spend: 96.40 })}
    />
  );
  // Down $12.28 — the consequence of yesterday's spending.
  expect(screen.getByText(/\$12\.28 vs\. yesterday/)).toBeInTheDocument();
});

test('omits the delta when yesterday is unavailable', () => {
  render(<SafeToSpendCard data={payload()} yesterday={{ available: false }} />);
  expect(screen.queryByText(/vs\. yesterday/)).toBeNull();
});

test('omits the delta when the number did not move', () => {
  render(
    <SafeToSpendCard data={payload()} yesterday={payload()} />
  );
  expect(screen.queryByText(/vs\. yesterday/)).toBeNull();
});
