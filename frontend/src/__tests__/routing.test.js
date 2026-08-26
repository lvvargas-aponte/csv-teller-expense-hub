import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import App from '../App';
import { ACTIVE_TAB_KEY } from '../legacyRoutes';
import { ALL_PATHS } from '../navConfig';

jest.mock('axios');

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  // Most endpoints are happy with an empty array; a couple of pages
  // destructure specific shapes off the response and would throw on that
  // generic default, which would make the route-coverage test below fail
  // for reasons unrelated to routing.
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/sync/shared-rows')) return Promise.resolve({ data: { rows: [] } });
    if (url.includes('/api/subscriptions')) {
      return Promise.resolve({
        data: { subscriptions: [], summary: { needs_review_count: 0, active_monthly_cost: 0, cancel_monthly_savings: 0 } },
      });
    }
    return Promise.resolve({ data: [] });
  });
  axios.post.mockResolvedValue({ data: {} });
});

const renderAt = (path) => render(
  <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>,
);

test.each([
  ['/accounts', 'Accounts'],
  ['/invest', 'Invest'],
  ['/plan/budgets', 'Budgets'],
  ['/plan/goals', 'Goals'],
  ['/ask', 'Ask'],
])('%s renders its own page heading', async (path, heading) => {
  renderAt(path);
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });
});

test('an unknown path falls back to Home rather than a blank page', async () => {
  renderAt('/nope');
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument();
  });
});

test('/finances redirects to Home', async () => {
  renderAt('/finances');
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument();
  });
});

test('a returning user holding a stored tab lands on its route', async () => {
  localStorage.setItem(ACTIVE_TAB_KEY, 'budgets');
  renderAt('/');
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: 'Budgets' })).toBeInTheDocument();
  });
  expect(localStorage.getItem(ACTIVE_TAB_KEY)).toBeNull();
});

test('a deliberate Home click is not hijacked by a stored legacy tab', async () => {
  // LegacyTabRedirect must only fire on first mount. Deep-linking to
  // /accounts leaves the stored key in place (early return, wrong pathname);
  // clicking Home afterward must land on Home, not re-trigger the redirect.
  localStorage.setItem(ACTIVE_TAB_KEY, 'budgets');
  renderAt('/accounts');
  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: 'Accounts' })).toBeInTheDocument();
  });

  await userEvent.click(screen.getByRole('link', { name: 'Home' }));

  await waitFor(() => {
    expect(screen.getByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument();
  });
});

test.each(ALL_PATHS.filter((p) => p !== '/'))(
  '%s does not silently bounce to the Home fallback',
  async (path) => {
    renderAt(path);
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 1, name: 'Home' })).toBeNull();
    });
  },
);

test('insight actions point at real routes, not the pre-Phase-2 ones', () => {
  const { buildInsights } = require('../utils/insightBuilder');

  // Fixtures crafted to actually trip both rules whose targets changed:
  // ruleUncategorized needs >$500 uncategorized spend this month, and
  // ruleSpendingHigh needs a >=10% jump over the prior month's total.
  const now = new Date();
  const monthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const transactions = [
    {
      date: `${monthKey}-05`, amount: -600, transaction_type: 'debit', category: '',
    },
  ];
  const dashboard = {
    monthly_totals: [
      { month: 'prior', total: 1000 },
      { month: 'current', total: 1500 },
    ],
  };

  const insights = buildInsights({ transactions, dashboard });
  const routes = JSON.stringify(insights);

  // Both rules must actually have fired, or the assertion below proves nothing.
  expect(insights.length).toBeGreaterThanOrEqual(2);
  expect(routes).toMatch(/"route":"\/transactions"/);

  // "/" meant the transactions page before Phase 2 and means Home after it.
  expect(routes).not.toMatch(/"route":"\/"/);
});
