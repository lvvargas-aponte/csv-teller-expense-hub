import React from 'react';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import axios from 'axios';
import SyncModal from '../SyncModal';

jest.mock('axios');
jest.mock('../styles', () => ({
  modal: {}, modalHeader: {}, modalTitle: {}, modalSub: {}, closeBtn: {},
  modalBody: {}, modalFooter: {}, row2: {}, fieldGroup: {}, label: {},
  input: {}, btn: {}, btnSecondary: {}, btnTeller: {}, btnPrimary: {},
}));
jest.mock('../Backdrop', () => ({ onClose, children }) => (
  <div data-testid="backdrop">{children}</div>
));
jest.mock('../Spin', () => () => <span data-testid="spin" />);

const mockAccounts = [
  { id: 'acct_1', name: 'Checking',  subtype: 'checking',  type: 'depository', institution: { name: 'First Bank' } },
  { id: 'acct_2', name: 'Savings',   subtype: 'savings',   type: 'depository', institution: { name: 'First Bank' } },
  { id: 'acct_3', name: 'Platinum',  subtype: 'credit_card', type: 'credit',   institution: { name: 'Second Bank' } },
];

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: mockAccounts });
});

function renderModal(handlers = {}) {
  return render(<SyncModal onSync={jest.fn()} onClose={jest.fn()} {...handlers} />);
}

// ── Rendering ────────────────────────────────────────────────────────────────

test('renders modal title', async () => {
  renderModal();
  expect(screen.getByText(/Sync Bank Transactions/)).toBeInTheDocument();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

test('renders date inputs', async () => {
  renderModal();
  const dateInputs = screen.getAllByDisplayValue(/-/);
  expect(dateInputs.length).toBeGreaterThanOrEqual(2);
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

test('renders preset buttons', async () => {
  renderModal();
  expect(screen.getByText('Previous month')).toBeInTheDocument();
  expect(screen.getByText('This month')).toBeInTheDocument();
  expect(screen.getByText('Custom range')).toBeInTheDocument();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

test('Cancel button calls onClose', async () => {
  const mockClose = jest.fn();
  renderModal({ onClose: mockClose });
  fireEvent.click(screen.getByText('Cancel'));
  expect(mockClose).toHaveBeenCalled();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

test('close (✕) button calls onClose', async () => {
  const mockClose = jest.fn();
  renderModal({ onClose: mockClose });
  fireEvent.click(screen.getByText('✕'));
  expect(mockClose).toHaveBeenCalled();
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

// ── Account list ──────────────────────────────────────────────────────────────

test('shows all accounts grouped by institution', async () => {
  renderModal();
  expect(await screen.findByText('Checking')).toBeInTheDocument();
  expect(screen.getByText('Savings')).toBeInTheDocument();
  expect(screen.getByText('Platinum')).toBeInTheDocument();
  expect(screen.getByText('First Bank')).toBeInTheDocument();
  expect(screen.getByText('Second Bank')).toBeInTheDocument();
});

test('all accounts are checked by default', async () => {
  renderModal();
  await screen.findByText('Checking');
  const checkboxes = screen.getAllByRole('checkbox');
  // first checkbox is "All", rest are per-account
  checkboxes.slice(1).forEach((cb) => expect(cb).toBeChecked());
});

test('All checkbox unchecks all accounts', async () => {
  renderModal();
  await screen.findByText('Checking');
  const allCb = screen.getAllByRole('checkbox')[0];
  fireEvent.click(allCb);
  screen.getAllByRole('checkbox').slice(1).forEach((cb) => expect(cb).not.toBeChecked());
});

test('unchecking one account unchecks it individually', async () => {
  renderModal();
  await screen.findByText('Checking');
  const checkboxes = screen.getAllByRole('checkbox');
  fireEvent.click(checkboxes[1]); // uncheck first account
  expect(checkboxes[1]).not.toBeChecked();
  expect(checkboxes[2]).toBeChecked();
});

test('Sync button is disabled when no accounts are selected', async () => {
  renderModal();
  await screen.findByText('Checking');
  // Uncheck all via the All checkbox
  const allCb = screen.getAllByRole('checkbox')[0];
  fireEvent.click(allCb);
  expect(screen.getByRole('button', { name: /Sync/ })).toBeDisabled();
});

// ── Sync call ─────────────────────────────────────────────────────────────────

test('Sync button calls onSync with dates and all account IDs when all selected', async () => {
  const mockSync = jest.fn();
  renderModal({ onSync: mockSync });
  await screen.findByText('Checking');

  fireEvent.click(screen.getByRole('button', { name: /Sync/ }));
  expect(mockSync).toHaveBeenCalledWith(
    expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    expect.arrayContaining(['acct_1', 'acct_2', 'acct_3']),
  );
});

test('Sync passes only selected account IDs when subset chosen', async () => {
  const mockSync = jest.fn();
  renderModal({ onSync: mockSync });
  await screen.findByText('Checking');

  // Uncheck acct_2 (Savings, second account checkbox)
  const checkboxes = screen.getAllByRole('checkbox');
  fireEvent.click(checkboxes[2]);

  fireEvent.click(screen.getByRole('button', { name: /Sync/ }));
  const [, , accountIds] = mockSync.mock.calls[0];
  expect(accountIds).toContain('acct_1');
  expect(accountIds).not.toContain('acct_2');
  expect(accountIds).toContain('acct_3');
});

test('Previous month preset fills in date range', async () => {
  const { container } = renderModal();
  fireEvent.click(screen.getByText('Previous month'));
  const dateInputs = within(container).getAllByDisplayValue(/-/);
  expect(dateInputs[0].value).toMatch(/^\d{4}-\d{2}-01$/);
  expect(dateInputs[1].value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
});

test('shows fallback message when account fetch fails', async () => {
  axios.get.mockRejectedValue(new Error('Network error'));
  renderModal();
  expect(await screen.findByText(/No accounts found/)).toBeInTheDocument();
});
