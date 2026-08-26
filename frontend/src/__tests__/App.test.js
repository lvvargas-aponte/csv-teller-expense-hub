import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import App from '../App';

// '/' is Home after Phase 2 routing; these tests exercise the transactions
// review queue, which now lives at /transactions.
const renderApp = () => render(
  <MemoryRouter initialEntries={['/transactions']}><App /></MemoryRouter>,
);

jest.mock('axios');

const mockTransactions = [
  {
    id: 't1', transaction_id: 't1',
    date: '2024-01-15', description: 'STARBUCKS', amount: -4.50,
    source: 'discover', institution: 'Discover',
    is_shared: false, reviewed: false,
    person_1_owes: 0, person_2_owes: 0, notes: '', transaction_type: 'debit',
  },
  {
    id: 't2', transaction_id: 't2',
    date: '2024-01-16', description: 'AMAZON PRIME', amount: -29.99,
    source: 'discover', institution: 'Discover',
    // reviewed MUST stay false: Current is a review queue and filters
    // reviewed rows out (App.js), so a reviewed fixture would be invisible
    // here and every filter assertion below would silently pass for the
    // wrong reason. Reviewed rows are History's job. Marking a txn shared
    // doesn't auto-review it, so shared+unreviewed is the natural state.
    is_shared: true, reviewed: false,
    person_1_owes: 15.00, person_2_owes: 15.00, notes: '', transaction_type: 'debit',
  },
];

const mockPersonNames = { person_1: 'Alice', person_2: 'Bob' };

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: mockTransactions });
    if (url.includes('person-names'))    return Promise.resolve({ data: mockPersonNames });
    if (url.includes('/api/accounts'))   return Promise.resolve({ data: [] });
    if (url.includes('/api/balances/summary')) return Promise.resolve({ data: { accounts: [] } });
    if (url.includes('/api/categories'))       return Promise.resolve({ data: { categories: [] } });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
});

// ── Initial load ──────────────────────────────────────────────────────────────

test('renders transaction descriptions after load', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('Current hides reviewed transactions — they live on History', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: [
      ...mockTransactions,
      { id: 't3', transaction_id: 't3', date: '2024-01-17', description: 'ALREADY_REVIEWED',
        amount: -9.99, source: 'discover', institution: 'Discover',
        is_shared: false, reviewed: true,
        person_1_owes: 0, person_2_owes: 0, notes: '', transaction_type: 'debit' },
    ] });
    if (url.includes('person-names')) return Promise.resolve({ data: mockPersonNames });
    if (url.includes('/api/accounts')) return Promise.resolve({ data: [] });
    if (url.includes('/api/balances/summary')) return Promise.resolve({ data: { accounts: [] } });
    if (url.includes('/api/categories')) return Promise.resolve({ data: { categories: [] } });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });

  renderApp();
  await screen.findByText('STARBUCKS');
  expect(screen.queryByText('ALREADY_REVIEWED')).not.toBeInTheDocument();
});

test('shows total transaction count in stat pill', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  // total stat pill renders the count (2) followed by "total".
  expect(screen.getByText('total')).toBeInTheDocument();
});

test('Unreviewed pill counts only un-reviewed (reviewed=false) transactions', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: [
      { id: 't1', transaction_id: 't1', date: '2024-01-15', description: 'UNTOUCHED',
        amount: -1, source: 'discover', institution: 'Discover',
        is_shared: false, reviewed: false,
        person_1_owes: 0, person_2_owes: 0, notes: '', transaction_type: 'debit' },
      { id: 't2', transaction_id: 't2', date: '2024-01-16', description: 'MARKED_PERSONAL',
        amount: -2, source: 'discover', institution: 'Discover',
        is_shared: false, reviewed: true,
        person_1_owes: 0, person_2_owes: 0, notes: '', transaction_type: 'debit' },
      { id: 't3', transaction_id: 't3', date: '2024-01-17', description: 'SHARED',
        amount: -3, source: 'discover', institution: 'Discover',
        is_shared: true, reviewed: true,
        person_1_owes: 1.5, person_2_owes: 1.5, notes: '', transaction_type: 'debit' },
    ] });
    if (url.includes('person-names')) return Promise.resolve({ data: mockPersonNames });
    if (url.includes('/api/accounts'))  return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });

  renderApp();
  await screen.findByText('UNTOUCHED');

  // The unreviewed pill renders the count and the literal word "unreviewed"
  // in adjacent spans. Find by the pill's accessible test id.
  const pill = screen.getByTestId('stat-pill-unreviewed');
  expect(pill.textContent).toMatch(/(^|\D)1(\D|$)/);
});

test('shows error banner when load fails', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts')) return Promise.resolve({ data: [] });
    return Promise.reject(new Error('Network Error'));
  });
  renderApp();
  await screen.findByText(/Could not load transactions/);
});

test('error banner can be dismissed', async () => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts')) return Promise.resolve({ data: [] });
    return Promise.reject(new Error('Network Error'));
  });
  renderApp();
  await screen.findByText(/Could not load transactions/);
  fireEvent.click(screen.getByLabelText('Dismiss error'));
  await waitFor(() =>
    expect(screen.queryByText(/Could not load transactions/)).not.toBeInTheDocument()
  );
});

// ── Filters ───────────────────────────────────────────────────────────────────

test('filter by shared shows only shared transactions', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  fireEvent.change(screen.getByLabelText('Filter by type'), { target: { value: 'shared' } });
  expect(screen.queryByText('STARBUCKS')).not.toBeInTheDocument();
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('filter by personal shows only personal transactions', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  fireEvent.change(screen.getByLabelText('Filter by type'), { target: { value: 'personal' } });
  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
  expect(screen.queryByText('AMAZON PRIME')).not.toBeInTheDocument();
});

// ── Sync flow ─────────────────────────────────────────────────────────────────

test('clicking Sync Banks opens the sync modal', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  fireEvent.click(screen.getByRole('button', { name: /Sync Banks/ }));
  expect(screen.getByText(/Sync Bank Transactions/)).toBeInTheDocument();
});
