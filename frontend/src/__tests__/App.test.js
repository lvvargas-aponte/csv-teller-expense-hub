import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import App from '../App';

const renderApp = () => render(<MemoryRouter><App /></MemoryRouter>);

jest.mock('axios');

jest.mock('../components/ui/styles', () => ({
  root: {}, header: {}, headerInner: {}, brand: {}, brandIcon: {},
  headerActions: {}, btn: {}, btnTeller: {}, btnGreen: {}, btnSecondary: {},
  main: {}, errorBanner: {}, toastClose: {},
  statsBar: {}, statCard: {}, statVal: {}, statLabel: {},
  toolbar: {}, filters: {}, select: {}, bulkBar: {}, bulkCount: {},
  tableWrap: {}, table: {}, th: {}, row: {}, rowSelected: {}, rowShared: {},
  td: {}, badge: {}, sharedBadge: {}, personalBadge: {},
  actionGroup: {}, inlineToggle: {}, toggleBtn: {},
  toggleBtnActivePersonal: {}, toggleBtnActiveShared: {}, editBtn: {},
  empty: {}, modal: {}, modalHeader: {}, modalTitle: {}, modalSub: {},
  closeBtn: {}, modalBody: {}, modalFooter: {}, toggleRow: {}, segmented: {},
  seg: {}, segActive: {}, row2: {}, splitRow: {}, splitBtn: {}, fieldGroup: {},
  label: {}, input: {}, toast: {},
}));

const mockTransactions = [
  {
    id: 't1', transaction_id: 't1',
    date: '2024-01-15', description: 'STARBUCKS', amount: -4.50,
    source: 'discover', is_shared: false, reviewed: false,
    person_1_owes: 0, person_2_owes: 0, notes: '',
  },
  {
    id: 't2', transaction_id: 't2',
    date: '2024-01-16', description: 'AMAZON PRIME', amount: -29.99,
    source: 'discover', is_shared: true, reviewed: true,
    person_1_owes: 15.00, person_2_owes: 15.00, notes: '',
  },
];

const mockPersonNames = { person_1: 'Alice', person_2: 'Bob' };

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: mockTransactions });
    if (url.includes('person-names'))    return Promise.resolve({ data: mockPersonNames });
    if (url.includes('/api/accounts'))   return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
});

// ── Initial load ──────────────────────────────────────────────────────────────

test('renders transaction descriptions after load', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('shows total transaction count in stat card', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  expect(screen.getByText('2')).toBeInTheDocument();
});

test('shows shared count in stat card', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  const ones = screen.getAllByText('1');
  expect(ones.length).toBeGreaterThanOrEqual(1);
});

test('Unreviewed tile counts only untouched (reviewed=false) transactions', async () => {
  // t1: untouched (reviewed=false) — should count as unreviewed.
  // t2: user-marked-Personal earlier (reviewed=true, is_shared=false) — should NOT count.
  // t3: shared (reviewed=true) — should NOT count.
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: [
      { id: 't1', transaction_id: 't1', date: '2024-01-15', description: 'UNTOUCHED',
        amount: -1, source: 'discover', is_shared: false, reviewed: false,
        person_1_owes: 0, person_2_owes: 0, notes: '' },
      { id: 't2', transaction_id: 't2', date: '2024-01-16', description: 'MARKED_PERSONAL',
        amount: -2, source: 'discover', is_shared: false, reviewed: true,
        person_1_owes: 0, person_2_owes: 0, notes: '' },
      { id: 't3', transaction_id: 't3', date: '2024-01-17', description: 'SHARED',
        amount: -3, source: 'discover', is_shared: true, reviewed: true,
        person_1_owes: 1.5, person_2_owes: 1.5, notes: '' },
    ] });
    if (url.includes('person-names')) return Promise.resolve({ data: mockPersonNames });
    if (url.includes('/api/accounts'))  return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });

  renderApp();
  await screen.findByText('UNTOUCHED');

  // Find the Unreviewed stat card by its label, then read the sibling value.
  const unreviewedLabel = screen.getByText('Unreviewed');
  const card = unreviewedLabel.closest('[class*="stat-card"]') || unreviewedLabel.parentElement;
  expect(card.textContent).toMatch(/(^|\D)1(\D|$)/);
});

test('shows error banner when load fails', async () => {
  axios.get.mockRejectedValue(new Error('Network Error'));
  renderApp();
  await screen.findByText(/Could not load transactions/);
});

test('error banner can be dismissed', async () => {
  axios.get.mockRejectedValue(new Error('Network Error'));
  renderApp();
  await screen.findByText(/Could not load transactions/);
  fireEvent.click(screen.getByText('✕'));
  await waitFor(() =>
    expect(screen.queryByText(/Could not load transactions/)).not.toBeInTheDocument()
  );
});

// ── Filters ───────────────────────────────────────────────────────────────────

test('filter by shared shows only shared transactions', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');

  fireEvent.click(screen.getByRole('combobox', { name: 'Filter by type' }));
  fireEvent.mouseDown(screen.getByRole('option', { name: 'Shared only' }));

  expect(screen.queryByText('STARBUCKS')).not.toBeInTheDocument();
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('filter by personal shows only personal transactions', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');

  fireEvent.click(screen.getByRole('combobox', { name: 'Filter by type' }));
  fireEvent.mouseDown(screen.getByRole('option', { name: 'Personal only' }));

  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
  expect(screen.queryByText('AMAZON PRIME')).not.toBeInTheDocument();
});

// ── Sync modal ────────────────────────────────────────────────────────────────

test('clicking Sync Banks opens the sync modal', async () => {
  renderApp();
  await screen.findByText('STARBUCKS');
  fireEvent.click(screen.getByRole('button', { name: /Sync Banks/ }));
  expect(screen.getByText(/Sync Bank Transactions/)).toBeInTheDocument();
});
