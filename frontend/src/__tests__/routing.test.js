import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import App from '../App';
import { ACTIVE_TAB_KEY } from '../legacyRoutes';
import { ALL_PATHS } from '../navConfig';
import { useSyncFlow } from '../hooks/useSyncFlow';

jest.mock('axios');

// Driving a real bank sync/CSV upload to completion through the UI in jsdom
// (date pickers, file input, awaited axios round-trips inside SyncModal /
// UploadCsvModal) isn't practical here. Instead this mocks useSyncFlow's
// return value directly so a test can assert the toast renders from the
// shell — i.e. it's still on screen after the route (and TransactionsPage)
// that started the sync has unmounted.
jest.mock('../hooks/useSyncFlow');

const baseSyncFlow = {
  syncing: false,
  uploading: false,
  sendingSheet: false,
  syncToast: null,
  setSyncToast: jest.fn(),
  showSyncModal: false,
  setShowSyncModal: jest.fn(),
  showAccountsModal: false,
  setShowAccountsModal: jest.fn(),
  pendingCsvFile: null,
  setPendingCsvFile: jest.fn(),
  accountsRefreshKey: 0,
  setAccountsRefreshKey: jest.fn(),
  syncBanks: jest.fn(),
  handleCsvPicked: jest.fn(),
  submitCsvUpload: jest.fn(),
  sendToSheet: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  useSyncFlow.mockReturnValue(baseSyncFlow);
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

test('Ask shows the advisor by default', async () => {
  renderAt('/ask');
  expect(await screen.findByRole('heading', { level: 1, name: 'Ask' })).toBeInTheDocument();
  expect(screen.queryByText('External library')).toBeNull();
});

test('Ask memory is its own route', async () => {
  renderAt('/ask/memory');
  expect(await screen.findByRole('heading', { level: 1, name: 'Ask' })).toBeInTheDocument();
  expect(await screen.findByText('External library')).toBeInTheDocument();
});

test('Ask sub-nav renders exactly once, not once per nav surface', async () => {
  renderAt('/ask');
  const advisor = await screen.findAllByRole('link', { name: 'Advisor' });
  expect(advisor).toHaveLength(1);
  const memory = await screen.findAllByRole('link', { name: 'Memory' });
  expect(memory).toHaveLength(1);
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

test('commitments due-soon shows bills and recurring charges together', async () => {
  renderAt('/plan/commitments/due');
  expect(await screen.findByRole('heading', { level: 1, name: 'Commitments' })).toBeInTheDocument();
  expect(await screen.findByText('Upcoming Bills')).toBeInTheDocument();
  expect(await screen.findByText('Recurring Charges')).toBeInTheDocument();
});

test('commitments recurring shows subscriptions', async () => {
  renderAt('/plan/commitments/recurring');
  expect(await screen.findByRole('heading', { level: 1, name: 'Commitments' })).toBeInTheDocument();
  expect(await screen.findByText(/subscriptions & recurring charges/i)).toBeInTheDocument();
});

test('the bare commitments path lands on due soon', async () => {
  renderAt('/plan/commitments');
  expect(await screen.findByText('Upcoming Bills')).toBeInTheDocument();
});

test('commitments sub-tabs are real links, not buttons', async () => {
  // Buttons can't be ctrl/cmd-clicked, middle-clicked, or right-clicked for
  // "copy link address" — the whole point of these being routes.
  renderAt('/plan/commitments/due');
  const due = await screen.findByRole('link', { name: 'Due soon' });
  const recurring = await screen.findByRole('link', { name: 'Recurring' });
  expect(due).toHaveAttribute('href', '/plan/commitments/due');
  expect(recurring).toHaveAttribute('href', '/plan/commitments/recurring');
});

test('each commitments view fetches only what it shows', async () => {
  // Stacking all three sections made every visit fire all three fetches.
  // Splitting them is the point; assert it actually happened. axios is
  // already mocked module-wide above, so this needs no extra mocking —
  // just check the URL never reaches the subscriptions endpoint.
  renderAt('/plan/commitments/due');
  await screen.findByText('Upcoming Bills');
  const subscriptionCalls = axios.get.mock.calls.filter(([url]) => url.includes('/api/subscriptions'));
  expect(subscriptionCalls).toHaveLength(0);
});

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

test('a sync toast survives navigating away from transactions', async () => {
  const user = userEvent.setup();
  useSyncFlow.mockReturnValue({
    ...baseSyncFlow,
    syncToast: { total_new: 3, from_date: '2026-08-01', to_date: '2026-08-25', details: [] },
  });
  renderAt('/transactions');

  expect(screen.getByTestId('sync-toast')).toBeInTheDocument();

  await user.click(await screen.findByRole('link', { name: 'Accounts' }));

  expect(screen.getByRole('heading', { level: 1, name: 'Accounts' })).toBeInTheDocument();
  expect(screen.queryByTestId('sync-toast')).toBeInTheDocument();
});
