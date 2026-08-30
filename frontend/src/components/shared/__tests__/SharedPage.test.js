import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SharedPage from '../SharedPage';
import {
  getSharedRows,
  getSyncStatus,
  syncShared,
  acknowledgeCorrection,
  setDispute,
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
    category: 'housing',
    account: 'Chase',
    you_owe: null,
    they_owe: null,
    split_label: null,
    reviewed: true,
    publishable: true,
    blocked_reason: null,
    dispute_flag: null,
    dispute_by: null,
    dispute_note: null,
    synced_at: '2026-06-15T14:32:05Z',
    ...overrides,
  };
}

function settlement(overrides = {}) {
  return {
    you_owe_total: 0,
    they_owe_total: 0,
    net: 0,
    direction: 'even',
    counted_count: 0,
    counted_amount: 0,
    blocked_count: 0,
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

function mockRows(rows, me = ME, peer = PEER, settle = settlement()) {
  getSharedRows.mockResolvedValue({
    data: { period: '2026-06', me, peer, rows, settlement: settle },
  });
}

function mockStatus(overrides = {}) {
  getSyncStatus.mockResolvedValue({ data: statusBody(overrides) });
}

const rowOf = (id) => screen.getByTestId(`shared-row-${id}`);

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
  expect(within(rowOf('t1')).getByText('Valeria')).toBeInTheDocument();
  expect(within(rowOf('peer:x1')).getByText('Christy')).toBeInTheDocument();
});

test('a null you_owe leaves the settles column to the other side, never 0.00', async () => {
  mockRows([row({ you_owe: null, they_owe: 56.13 })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = rowOf('t1');
  expect(within(tr).getByText('Christy owes you')).toBeInTheDocument();
  expect(within(tr).getByText('$56.13')).toBeInTheDocument();
  expect(within(tr).queryByText('$0.00')).not.toBeInTheDocument();
  expect(within(tr).queryByText('You owe Christy')).not.toBeInTheDocument();
});

test('a row you paid says the peer owes you', async () => {
  mockRows([row({ who: 'Valeria', you_owe: null, they_owe: 56.13 })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = rowOf('t1');
  expect(within(tr).getByText('Christy owes you')).toBeInTheDocument();
  expect(within(tr).getByText('$56.13')).toBeInTheDocument();
});

test('a row they paid says you owe the peer', async () => {
  mockRows([row({ who: 'Christy', you_owe: 56.13, they_owe: null })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = rowOf('t1');
  expect(within(tr).getByText('You owe Christy')).toBeInTheDocument();
  expect(within(tr).getByText('$56.13')).toBeInTheDocument();
});

test('a publishable: false row shows its blocked_reason, a tag, and no settling figure', async () => {
  mockRows([row({
    transaction_id: 't2', publishable: false,
    blocked_reason: 'No split set for this row',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = rowOf('t2');
  expect(within(tr).getByText(/No split set for this row/)).toBeInTheDocument();
  expect(within(tr).getByText(/can't publish/i)).toBeInTheDocument();
  expect(within(tr).getByText(/not counted/i)).toBeInTheDocument();
});

test('a row omits empty meta rather than rendering a dash for it', async () => {
  mockRows([
    row({ category: null, account: null, split_label: null }),
    row({
      transaction_id: 't2', description: 'Costco',
      category: 'groceries', account: 'Chase', split_label: '50 / 50 split',
    }),
  ]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const bare = rowOf('t1');
  expect(within(bare).queryByText('—')).not.toBeInTheDocument();
  expect(within(bare).queryByText('Groceries')).not.toBeInTheDocument();

  const full = rowOf('t2');
  expect(within(full).getByText('Chase')).toBeInTheDocument();
  expect(within(full).getByText('Groceries')).toBeInTheDocument();
  expect(within(full).getByText('50 / 50 split')).toBeInTheDocument();
});

test('a disputed row shows the disputer and note', async () => {
  mockRows([row({
    transaction_id: 't3', dispute_flag: 'Y',
    dispute_by: 'Christy', dispute_note: 'that was mine',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const tr = rowOf('t3');
  expect(within(tr).getByText(/Christy/)).toBeInTheDocument();
  expect(within(tr).getByText(/that was mine/)).toBeInTheDocument();
});

test('an unparseable date renders the raw string in its day header, never "Invalid Date"', async () => {
  mockRows([row({
    transaction_id: 't4', publishable: false,
    date: 'not-a-date', blocked_reason: 'Date could not be parsed',
  })]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  const group = screen.getByTestId('day-group-not-a-date');
  expect(within(group).getByText('not-a-date')).toBeInTheDocument();
  expect(within(group).queryByText(/Invalid Date/)).not.toBeInTheDocument();
});

test('renders without a peer and falls back sensibly in the legend', async () => {
  mockRows([row()], ME, null);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  expect(screen.getAllByText(/peer/i).length).toBeGreaterThan(0);
});

test('dismissing a correction calls acknowledgeCorrection and removes it from the list', async () => {
  mockStatus({
    corrections: [
      { id: 5, period: '2026-06', txn_id: 'u1:t9', column_name: 'Amount', sheet_value: '9.99', app_value: '112.25' },
    ],
  });
  acknowledgeCorrection.mockResolvedValue({ data: { acknowledged: true } });

  render(<SharedPage />);

  expect(await screen.findByText(/112\.25/)).toBeInTheDocument();

  const dismissBtn = screen.getByRole('button', { name: /^dismiss correction/i });
  await userEvent.click(dismissBtn);

  await waitFor(() => expect(acknowledgeCorrection).toHaveBeenCalledWith(5));
  await waitFor(() => expect(screen.queryByText(/112\.25/)).not.toBeInTheDocument());
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

test('a refused sync still refreshes the status line, instead of leaving a stale success banner', async () => {
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

test('an error sync response also refreshes the status line', async () => {
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

test('a successful sync shows the result and refetches, picking up rows the sync just wrote', async () => {
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

  const line = await screen.findByRole('status');
  expect(line).toHaveTextContent('2 sent, 3 received');

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(2));
  expect(await screen.findByText('Just synced')).toBeInTheDocument();
});

test('a sync that pushed a dispute includes it in the status line', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'ok',
      results: [{ rows_pushed: 2, rows_pulled: 3, disputes_pushed: 1 }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(1));
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  const line = await screen.findByRole('status');
  expect(line).toHaveTextContent('2 sent, 3 received');
  expect(line).toHaveTextContent(/1 dispute/);
});

test('a sync with no dispute writes leaves the status line unchanged', async () => {
  syncShared.mockResolvedValue({
    data: {
      status: 'ok',
      results: [{ rows_pushed: 2, rows_pulled: 3, disputes_pushed: 0 }],
    },
  });

  render(<SharedPage />);

  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(1));
  const syncBtn = screen.getByRole('button', { name: /sync now/i });
  await userEvent.click(syncBtn);

  const line = await screen.findByRole('status');
  expect(line).toHaveTextContent('2 sent, 3 received');
  expect(line).not.toHaveTextContent(/dispute/);
});

test('raising a dispute on a peer row calls the API with txn_id, flag and note, then refetches', async () => {
  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP',
    }),
  ]);
  setDispute.mockResolvedValue({ data: {} });

  render(<SharedPage />);

  await screen.findByText('UBER *TRIP');
  const disputeBtn = screen.getByRole('button', { name: /dispute uber \*trip/i });
  await userEvent.click(disputeBtn);

  const noteField = screen.getByLabelText(/dispute note/i);
  await userEvent.type(noteField, 'that was mine');

  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP', dispute_flag: 'Y', dispute_by: 'Valeria', dispute_note: 'that was mine',
    }),
  ]);

  const saveBtn = screen.getByRole('button', { name: /save/i });
  await userEvent.click(saveBtn);

  await waitFor(() => expect(setDispute).toHaveBeenCalledWith('peer:x1', { flag: 'Y', note: 'that was mine' }));
  await waitFor(() => expect(getSharedRows).toHaveBeenCalledTimes(2));
  expect(await screen.findByText(/you disputed this/i)).toBeInTheDocument();
});

test('withdrawing a dispute sends flag: null', async () => {
  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP', dispute_flag: 'Y', dispute_by: 'Valeria', dispute_note: 'that was mine',
    }),
  ]);
  setDispute.mockResolvedValue({ data: {} });

  render(<SharedPage />);

  await screen.findByText(/you disputed this/i);
  const withdrawBtn = screen.getByRole('button', { name: /withdraw dispute for uber \*trip/i });
  await userEvent.click(withdrawBtn);

  await waitFor(() => expect(setDispute).toHaveBeenCalledWith('peer:x1', { flag: null, note: null }));
});

test('our own row disputed by the peer shows their note read-only, with no clear control', async () => {
  mockRows([
    row({
      transaction_id: 't1', owner: 'me', owner_name: 'Valeria',
      dispute_flag: 'Y', dispute_by: 'Christy', dispute_note: 'that was mine',
    }),
  ]);

  render(<SharedPage />);

  await screen.findByText(/christy is disputing this/i);
  expect(screen.getByText(/that was mine/)).toBeInTheDocument();
  const tr = rowOf('t1');
  expect(within(tr).queryByRole('button', { name: /withdraw/i })).not.toBeInTheDocument();
  expect(within(tr).queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
  expect(within(tr).queryByRole('button', { name: /dispute/i })).not.toBeInTheDocument();
});

test('a failed dispute call surfaces an error and does not leave the row looking disputed', async () => {
  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP',
    }),
  ]);
  setDispute.mockRejectedValue({ response: { data: { detail: 'Could not save dispute' } } });

  render(<SharedPage />);

  await screen.findByText('UBER *TRIP');
  const disputeBtn = screen.getByRole('button', { name: /dispute uber \*trip/i });
  await userEvent.click(disputeBtn);

  const noteField = screen.getByLabelText(/dispute note/i);
  await userEvent.type(noteField, 'that was mine');

  const saveBtn = screen.getByRole('button', { name: /save/i });
  await userEvent.click(saveBtn);

  expect(await screen.findByText(/could not save dispute/i)).toBeInTheDocument();
  expect(screen.queryByText(/you disputed this/i)).not.toBeInTheDocument();
});

test('a dispute resolved to N on our own row is not shown as active', async () => {
  mockRows([
    row({
      transaction_id: 't1', owner: 'me', owner_name: 'Valeria',
      dispute_flag: 'N', dispute_by: 'Christy', dispute_note: 'withdrawn',
    }),
  ]);

  render(<SharedPage />);

  await screen.findByText('Cleaning');
  expect(screen.queryByText(/is disputing this/i)).not.toBeInTheDocument();
});

test('a dispute resolved to N on a peer row offers Dispute again, not Edit/Withdraw', async () => {
  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP', dispute_flag: 'N', dispute_by: 'Valeria', dispute_note: 'withdrawn',
    }),
  ]);

  render(<SharedPage />);

  await screen.findByText('UBER *TRIP');
  expect(screen.queryByText(/you disputed this/i)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /dispute uber \*trip/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
});

test('editing an existing dispute note preserves the current flag rather than forcing Y', async () => {
  mockRows([
    row({
      transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
      description: 'UBER *TRIP', dispute_flag: 'Y', dispute_by: 'Valeria', dispute_note: 'that was mine',
    }),
  ]);
  setDispute.mockResolvedValue({ data: {} });

  render(<SharedPage />);

  await screen.findByText(/you disputed this/i);
  const editBtn = screen.getByRole('button', { name: /edit dispute for uber \*trip/i });
  await userEvent.click(editBtn);

  const noteField = screen.getByLabelText(/dispute note/i);
  expect(noteField).toHaveValue('that was mine');
  await userEvent.clear(noteField);
  await userEvent.type(noteField, 'updated note');

  const saveBtn = screen.getByRole('button', { name: /save/i });
  await userEvent.click(saveBtn);

  await waitFor(() => expect(setDispute).toHaveBeenCalledWith('peer:x1', { flag: 'Y', note: 'updated note' }));
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

describe('settle up', () => {
  test('a net in the peer\'s favour names them and shows both sides', async () => {
    mockRows([row()], ME, PEER, settlement({
      you_owe_total: 267.41, they_owe_total: 1274.7, net: 1007.29,
      direction: 'they_owe', counted_count: 8, counted_amount: 3084.2,
    }));

    render(<SharedPage />);

    const card = await screen.findByTestId('settle-up');
    expect(within(card).getByTestId('settle-net')).toHaveTextContent('$1,007.29');
    expect(within(card).getByText(/Christy owes you, net for/)).toBeInTheDocument();
    expect(within(card).getByText('$1,274.70')).toBeInTheDocument();
    expect(within(card).getByText('$267.41')).toBeInTheDocument();
    expect(within(card).getByText(/8 shared expenses/)).toBeInTheDocument();
    expect(within(card).getByText(/\$3,084\.20 counted this month/)).toBeInTheDocument();
  });

  test('a net in your favour reads as you owing, and counts the blocked rows out', async () => {
    mockRows([row()], ME, PEER, settlement({
      you_owe_total: 600.46, they_owe_total: 188.4, net: 412.06,
      direction: 'you_owe', counted_count: 6, counted_amount: 1577.72,
      blocked_count: 1,
    }));

    render(<SharedPage />);

    const card = await screen.findByTestId('settle-up');
    expect(within(card).getByTestId('settle-net')).toHaveTextContent('$412.06');
    expect(within(card).getByText(/You owe Christy, net for/)).toBeInTheDocument();
    expect(within(card).getByText(/1 not counted/)).toBeInTheDocument();
  });

  test('an even month reads as even at zero, with no bars to compare', async () => {
    mockRows([row()], ME, PEER, settlement({ counted_count: 2, counted_amount: 200 }));

    render(<SharedPage />);

    const card = await screen.findByTestId('settle-up');
    expect(within(card).getByTestId('settle-net')).toHaveTextContent('$0.00');
    expect(within(card).getByText(/You're even for/)).toBeInTheDocument();
    expect(within(card).queryByText(/owes you$/)).not.toBeInTheDocument();
  });
});

describe('filters', () => {
  function threeRows() {
    mockRows([
      row({ transaction_id: 't1', description: 'Cleaning' }),
      row({
        transaction_id: 'peer:x1', owner: 'peer', owner_name: 'Christy',
        description: 'UBER *TRIP', you_owe: 22.69,
      }),
      row({
        transaction_id: 't2', description: 'Delta Air Lines',
        publishable: false, blocked_reason: 'No split set — nothing to publish.',
      }),
    ]);
  }

  test('the peer chip narrows the list to their rows', async () => {
    threeRows();
    render(<SharedPage />);

    await screen.findByText('Cleaning');
    await userEvent.click(screen.getByRole('button', { name: /Christy's/ }));

    expect(screen.getByText('UBER *TRIP')).toBeInTheDocument();
    expect(screen.queryByText('Cleaning')).not.toBeInTheDocument();
    expect(screen.queryByText('Delta Air Lines')).not.toBeInTheDocument();
  });

  test('the yours chip narrows the list to your rows', async () => {
    threeRows();
    render(<SharedPage />);

    await screen.findByText('Cleaning');
    await userEvent.click(screen.getByRole('button', { name: /^Yours/ }));

    expect(screen.getByText('Cleaning')).toBeInTheDocument();
    expect(screen.queryByText('UBER *TRIP')).not.toBeInTheDocument();
  });

  test('the needs-attention chip keeps only rows that need a decision', async () => {
    threeRows();
    render(<SharedPage />);

    await screen.findByText('Cleaning');
    await userEvent.click(screen.getByRole('button', { name: /needs attention/i }));

    expect(screen.getByText('Delta Air Lines')).toBeInTheDocument();
    expect(screen.queryByText('Cleaning')).not.toBeInTheDocument();
    expect(screen.queryByText('UBER *TRIP')).not.toBeInTheDocument();
  });

  test('All restores the full list', async () => {
    threeRows();
    render(<SharedPage />);

    await screen.findByText('Cleaning');
    await userEvent.click(screen.getByRole('button', { name: /^Yours/ }));
    await userEvent.click(screen.getByRole('button', { name: /^All/ }));

    expect(screen.getByText('Cleaning')).toBeInTheDocument();
    expect(screen.getByText('UBER *TRIP')).toBeInTheDocument();
    expect(screen.getByText('Delta Air Lines')).toBeInTheDocument();
  });
});
