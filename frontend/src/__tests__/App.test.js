import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';
import App from '../App';

// Mock axios so no real HTTP calls are made
jest.mock('axios');

// Mock styles.js to prevent DOM injection side-effects in tests
jest.mock('../components/styles', () => ({
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
    source: 'discover', is_shared: false, person_1_owes: 0, person_2_owes: 0, notes: '',
  },
  {
    id: 't2', transaction_id: 't2',
    date: '2024-01-16', description: 'AMAZON PRIME', amount: -29.99,
    source: 'discover', is_shared: true, person_1_owes: 15.00, person_2_owes: 15.00, notes: '',
  },
];

const mockPersonNames = { person_1: 'Alice', person_2: 'Bob' };

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation((url) => {
    if (url.includes('transactions/all')) return Promise.resolve({ data: mockTransactions });
    if (url.includes('person-names'))    return Promise.resolve({ data: mockPersonNames });
    return Promise.reject(new Error(`Unexpected GET: ${url}`));
  });
});

// ---------------------------------------------------------------------------
// Initial load
// ---------------------------------------------------------------------------

test('renders transaction descriptions after load', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('shows total transaction count in stat card', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');
  // Total = 2
  expect(screen.getByText('2')).toBeInTheDocument();
});

test('shows shared count in stat card', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');
  // Shared = 1 (t2)
  const ones = screen.getAllByText('1');
  expect(ones.length).toBeGreaterThanOrEqual(1);
});

test('shows error banner when load fails', async () => {
  axios.get.mockRejectedValue(new Error('Network Error'));
  render(<App />);
  await screen.findByText(/Could not load transactions/);
});

test('error banner can be dismissed', async () => {
  axios.get.mockRejectedValue(new Error('Network Error'));
  render(<App />);
  await screen.findByText(/Could not load transactions/);
  fireEvent.click(screen.getByText('✕'));
  await waitFor(() =>
    expect(screen.queryByText(/Could not load transactions/)).not.toBeInTheDocument()
  );
});

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

test('filter by source hides non-matching transactions', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');

  const sourceFilter = screen.getByDisplayValue('All sources');
  fireEvent.change(sourceFilter, { target: { value: 'barclays' } });

  // Both transactions are from 'discover', so neither should appear
  expect(screen.queryByText('STARBUCKS')).not.toBeInTheDocument();
  expect(screen.queryByText('AMAZON PRIME')).not.toBeInTheDocument();
});

test('filter by shared shows only shared transactions', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');

  const sharedFilter = screen.getByDisplayValue('All types');
  fireEvent.change(sharedFilter, { target: { value: 'shared' } });

  expect(screen.queryByText('STARBUCKS')).not.toBeInTheDocument();
  expect(screen.getByText('AMAZON PRIME')).toBeInTheDocument();
});

test('filter by personal shows only personal transactions', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');

  const sharedFilter = screen.getByDisplayValue('All types');
  fireEvent.change(sharedFilter, { target: { value: 'personal' } });

  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
  expect(screen.queryByText('AMAZON PRIME')).not.toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// Sync banks modal
// ---------------------------------------------------------------------------

test('clicking Sync Banks opens the sync modal', async () => {
  render(<App />);
  await screen.findByText('STARBUCKS');
  fireEvent.click(screen.getByText('🏦 Sync Banks'));
  expect(screen.getByText(/Sync Bank Transactions/)).toBeInTheDocument();
});
