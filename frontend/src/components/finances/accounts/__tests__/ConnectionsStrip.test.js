import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConnectionsStrip from '../ConnectionsStrip';
import { disconnectAccount } from '../../../../api/accounts';

jest.mock('../../../../api/accounts');

// Same fixtures the deleted Settings ConnectionsPane tests used, ported
// here because this component absorbed that pane's institution list,
// removal dialog, and SimpleFIN Bridge guidance copy.
const health = {
  institutions: [
    { institution: 'Chase', status: 'connected', last_error: null },
    { institution: 'Bank of America', status: 'disconnected', last_error: 'Login required' },
    { institution: 'Discover', status: 'manual', last_error: null },
  ],
  broken: [{ institution: 'Bank of America', status: 'disconnected', last_error: 'Login required' }],
  connected: [{ institution: 'Chase', status: 'connected', last_error: null }],
};

const summary = {
  accounts: [
    { id: 'a1', institution: 'Chase', name: 'Total Checking' },
    { id: 'a2', institution: 'Chase', name: 'Prime Visa' },
    { id: 'a3', institution: 'Bank of America', name: 'Cash Rewards' },
  ],
};

function renderStrip(props = {}) {
  return render(
    <ConnectionsStrip health={health} summary={summary} onRefresh={jest.fn()} {...props} />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  disconnectAccount.mockResolvedValue({ data: {} });
});

test('a broken connection points at SimpleFIN Bridge rather than a dead button', async () => {
  const user = userEvent.setup();
  renderStrip();

  await user.click(screen.getByRole('button', { name: /manage connections/i }));

  const row = screen.getByRole('group', { name: 'Bank of America' });
  expect(within(row).getByText(/reconnect needed/i)).toBeInTheDocument();
  expect(within(row).getByText(/SimpleFIN Bridge account/i)).toBeInTheDocument();
  expect(within(row).queryByRole('button', { name: /^Reconnect$/ })).not.toBeInTheDocument();
});

test('removing an institution warns that history is kept, and detaches on confirm', async () => {
  const user = userEvent.setup();
  renderStrip();

  await user.click(screen.getByRole('button', { name: /manage connections/i }));

  const chaseRow = screen.getByRole('group', { name: 'Chase' });
  await user.click(within(chaseRow).getByRole('button', { name: 'Remove' }));

  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText(/past transactions are kept/i)).toBeInTheDocument();

  await user.click(within(dialog).getByRole('button', { name: 'Remove' }));

  // One call per account behind the institution, through the accounts API
  // module rather than a raw axios call.
  await waitFor(() => expect(disconnectAccount).toHaveBeenCalledTimes(2));
  expect(disconnectAccount).toHaveBeenCalledWith('a1');
  expect(disconnectAccount).toHaveBeenCalledWith('a2');
});

// FIX 2(b) — syncError is rendered verbatim, with no "Sync failed — " prefix
// stitched on. useSyncAll emits full sentences; the old prefix produced
// doubled-up text like "Sync failed — Sync failed — is the backend running?"
// and mislabelled a partial success ("Brokerages did not sync, but bank
// balances are up to date.") as a total failure.
test('a successful SimpleFIN-only sync shows no error text', () => {
  renderStrip({ syncError: null });
  expect(screen.queryByText(/sync failed/i)).not.toBeInTheDocument();
});

test('a partial (brokerage-only) failure reads as partial, not total', () => {
  renderStrip({ syncError: 'Brokerages did not sync, but bank balances are up to date.' });
  expect(screen.getByText('Brokerages did not sync, but bank balances are up to date.')).toBeInTheDocument();
  expect(screen.queryByText(/sync failed — /i)).not.toBeInTheDocument();
});

test('a total failure message renders without a doubled prefix', () => {
  renderStrip({ syncError: 'Sync failed — is the backend running?' });
  expect(screen.getByText('Sync failed — is the backend running?')).toBeInTheDocument();
  expect(screen.queryByText(/sync failed — sync failed/i)).not.toBeInTheDocument();
});

test('declining the removal dialog detaches nothing', async () => {
  const user = userEvent.setup();
  renderStrip();

  await user.click(screen.getByRole('button', { name: /manage connections/i }));

  const chaseRow = screen.getByRole('group', { name: 'Chase' });
  await user.click(within(chaseRow).getByRole('button', { name: 'Remove' }));

  const dialog = await screen.findByRole('dialog');
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(disconnectAccount).not.toHaveBeenCalled();
});
