import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SharedPage from '../SharedPage';
import {
  getSharedRows,
  getSyncStatus,
  syncShared,
  acknowledgeCorrection,
} from '../../../api/sync';

jest.mock('../../../api/sync');

const ME = { user_id: 'u1', display_name: 'Valeria', person_slot: 1 };
const PEER = { display_name: 'Christy', person_slot: 2 };

function row(overrides = {}) {
  return {
    transaction_id: 't1',
    owner: 'me',
    owner_name: 'Valeria',
    date: '2026-06-03',
    description: 'Cleaning',
    amount: 140.0,
    who: 'Valeria',
    notes: '',
    you_owe: null,
    they_owe: null,
    reviewed: true,
    publishable: true,
    blocked_reason: null,
    dispute_flag: null,
    dispute_by: null,
    dispute_note: null,
    synced_at: null,
    ...overrides,
  };
}

function statusBody(overrides = {}) {
  return {
    enabled: true,
    open_periods: ['2026-06'],
    last_run: {
      period: '2026-06',
      status: 'ok',
      rows_pushed: 2,
      rows_pulled: 3,
      started_at: '2026-06-15T14:32:00Z',
      finished_at: '2026-06-15T14:32:05Z',
      refusal_reason: null,
      error_detail: null,
    },
    last_successful_pull: null,
    publishable_rows: 0,
    refusal: null,
    corrections: [],
    disputes_against_me: [],
    ...overrides,
  };
}

function mockRows(rows, me = ME, peer = PEER) {
  getSharedRows.mockResolvedValue({ data: { period: '2026-06', me, peer, rows } });
}

function mockStatus(overrides = {}) {
  getSyncStatus.mockResolvedValue({ data: statusBody(overrides) });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockRows([]);
  mockStatus();
});

test('renders your row and the peer row, each labelled with its owner name', async () => {
  mockRows([
    row(),
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      date: '2026-06-07', description: 'UBER *TRIP', amount: 45.38,
      you_owe: 22.69, they_owe: null,
    }),
  ]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const yourRow = screen.getByRole('row', { name: /Cleaning/ });
  expect(within(yourRow).getByText('Valeria')).toBeInTheDocument();

  const theirRow = screen.getByRole('row', { name: /UBER \*TRIP/ });
  expect(within(theirRow).getByText('Christy')).toBeInTheDocument();
});

test('a null you_owe renders as an em dash, not 0.00', async () => {
  mockRows([row({ you_owe: null, they_owe: 56.13 })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = screen.getByRole('row', { name: /Cleaning/ });
  const cells = within(tr).getAllByRole('cell');
  expect(cells[4]).toHaveTextContent('—');
  expect(within(tr).queryByText('$0.00')).not.toBeInTheDocument();
});

test('a row you paid shows the peer amount under "They owe" and an em dash under "You owe"', async () => {
  mockRows([row({ who: 'Valeria', you_owe: null, they_owe: 56.13 })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = screen.getByRole('row', { name: /Cleaning/ });
  const cells = within(tr).getAllByRole('cell');
  expect(cells[4]).toHaveTextContent('—');
  expect(cells[5]).toHaveTextContent('$56.13');
});

test('a row they paid shows your amount under "You owe" and an em dash under "They owe"', async () => {
  mockRows([row({ who: 'Christy', you_owe: 56.13, they_owe: null })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = screen.getByRole('row', { name: /Cleaning/ });
  const cells = within(tr).getAllByRole('cell');
  expect(cells[4]).toHaveTextContent('$56.13');
  expect(cells[5]).toHaveTextContent('—');
});

test('a publishable: false row shows its blocked_reason', async () => {
  mockRows([row({
    transaction_id: 't2', publishable: false,
    blocked_reason: 'No split set for this row',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  expect(screen.getByText(/No split set for this row/)).toBeInTheDocument();
});

test('a disputed row shows the disputer and note', async () => {
  mockRows([row({
    transaction_id: 't3', dispute_flag: 'Y',
    dispute_by: 'Christy', dispute_note: 'that was mine',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = screen.getByRole('row', { name: /Cleaning/ });
  expect(within(tr).getByText(/Christy/)).toBeInTheDocument();
  expect(within(tr).getByText(/that was mine/)).toBeInTheDocument();
});

test('an unparseable date renders the raw string, never "Invalid Date"', async () => {
  mockRows([row({
    transaction_id: 't4', publishable: false,
    date: 'not-a-date', blocked_reason: 'Date could not be parsed',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = screen.getByRole('row', { name: /Cleaning/ });
  expect(within(tr).getByText('not-a-date')).toBeInTheDocument();
  expect(within(tr).queryByText(/Invalid Date/)).not.toBeInTheDocument();
});

test('renders without a peer and falls back sensibly in the legend', async () => {
  mockRows([row()], ME, null);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  expect(screen.getByText(/peer/i)).toBeInTheDocument();
});

test('dismissing a correction calls acknowledgeCorrection and removes it from the list', async () => {
  mockStatus({
    corrections: [
      { id: 5, period: '2026-06', txn_id: 'u1:t9', column_name: 'Amount', sheet_value: '9.99', app_value: '112.25' },
    ],
  });
  acknowledgeCorrection.mockResolvedValue({ data: { acknowledged: true } });

  render(<SharedPage />);

  const correctionText = await screen.findByText(/rewritten to 112\.25/);
  expect(correctionText).toBeInTheDocument();

  const dismissBtn = screen.getByRole('button', { name: /dismiss/i });
  await userEvent.click(dismissBtn);

  await waitFor(() => expect(acknowledgeCorrection).toHaveBeenCalledWith(5));
  await waitFor(() => expect(screen.queryByText(/rewritten to 112\.25/)).not.toBeInTheDocument());
});

test('a refused sync response surfaces refusal_message and does not show a success state', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'refused',
      results: [{ rows_pushed: 0, rows_pulled: 0, refusal_message: 'Christy already claimed this period.' }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalled());
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  expect(await screen.findByText(/Christy already claimed this period/)).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('an error sync response surfaces the error', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'error',
      results: [{ rows_pushed: 0, rows_pulled: 0, error_detail: 'Sheet API is unreachable.' }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalled());
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  expect(await screen.findByText(/Sheet API is unreachable/)).toBeInTheDocument();
});

test('a refused sync still refreshes the status strip, instead of leaving a stale success banner', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'refused',
      results: [{ rows_pushed: 0, rows_pulled: 0, refusal_message: 'Christy already claimed this period.' }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSyncStatus).toHaveBeenCalledTimes(1));
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  await screen.findByText(/Christy already claimed this period/);
  await waitFor(() => expect(getSyncStatus).toHaveBeenCalledTimes(2));
});

test('an error sync response also refreshes the status strip', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'error',
      results: [{ rows_pushed: 0, rows_pulled: 0, error_detail: 'Sheet API is unreachable.' }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSyncStatus).toHaveBeenCalledTimes(1));
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  await screen.findByText(/Sheet API is unreachable/);
  await waitFor(() => expect(getSyncStatus).toHaveBeenCalledTimes(2));
});

test('a successful sync shows the toast and refetches, picking up rows the sync just wrote', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'ok',
      results: [{ rows_pushed: 2, rows_pulled: 3 }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(1));

  mockRows([row({ transaction_id: 'new-from-sync', description: 'Just synced' })]);

  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  const toast = await screen.findByRole('status');
  expect(toast).toHaveTextContent('2 sent, 3 received');

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(2));
  expect(await screen.findByText('Just synced')).toBeInTheDocument();
});

test('changing the month refetches', async () => {
  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(1));
  const firstPeriod = getSharedRows.mock.calls[0][0];

  const select = screen.getByLabelText(/month/i);
  fireEvent.change(select, { target: { value: '2026-06' } });

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(2));
  expect(getSharedRows.mock.calls[1][0]).not.toBe(firstPeriod);
});
