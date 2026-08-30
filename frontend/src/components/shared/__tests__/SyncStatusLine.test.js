import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SyncStatusLine from '../SyncStatusLine';

function status(overrides = {}) {
  return {
    last_run: {
      period: '2026-06',
      status: 'ok',
      rows_pushed: 2,
      rows_pulled: 3,
      started_at: '2026-06-15T14:32:00Z',
      finished_at: '2026-06-15T14:32:05Z',
    },
    refusal: null,
    ...overrides,
  };
}

test('renders nothing when status has not loaded yet', () => {
  const { container } = render(<SyncStatusLine status={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('a successful last run shows success and the sent/received counts', () => {
  render(<SyncStatusLine status={status()} />);

  expect(screen.getByText(/synced/i)).toBeInTheDocument();
  expect(screen.getByText(/2 rows sent, 3 received/)).toBeInTheDocument();
});

test('a last run that did not succeed names its status instead of claiming success', () => {
  render(<SyncStatusLine status={status({
    last_run: { ...status().last_run, status: 'error' },
  })} />);

  expect(screen.getByText(/sync error/i)).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('a refusal renders the readable message, not the raw reason code', () => {
  render(<SyncStatusLine status={status({
    refusal: {
      reason: 'contract_version',
      message: 'Sync refused: the two instances speak different versions of the sheet contract.',
    },
  })} />);

  const refusal = screen.getByRole('alert');
  expect(refusal).toHaveTextContent(/two instances speak different versions/);
  expect(refusal).not.toHaveTextContent(/contract_version/);
});

test('with no run yet it says so and offers to sync', async () => {
  const onSync = jest.fn();
  render(<SyncStatusLine status={status({ last_run: null })} onSync={onSync} />);

  expect(screen.getByText(/no sync has run yet/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /sync now/i }));
  expect(onSync).toHaveBeenCalled();
});

test('a refusal from the sync just run outranks the stored last-run summary', async () => {
  const onDismiss = jest.fn();
  render(
    <SyncStatusLine
      status={status()}
      syncMessage={{ kind: 'refused', text: 'Christy already claimed this period.' }}
      onDismissMessage={onDismiss}
    />
  );

  const line = screen.getByRole('alert');
  expect(line).toHaveTextContent(/sync refused/i);
  expect(line).toHaveTextContent(/Christy already claimed this period/);
  expect(line).not.toHaveTextContent(/2 rows sent/);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /dismiss/i }));
  expect(onDismiss).toHaveBeenCalled();
});

test('a failed sync reads as failed rather than refused', () => {
  render(
    <SyncStatusLine
      status={status()}
      syncMessage={{ kind: 'error', text: 'Sheet API is unreachable.' }}
    />
  );

  expect(screen.getByRole('alert')).toHaveTextContent(/sync failed/i);
});

test('a successful sync announces its counts as a live status', () => {
  render(
    <SyncStatusLine
      status={status()}
      syncMessage={{ kind: 'ok', text: '2 sent, 3 received' }}
    />
  );

  expect(screen.getByRole('status')).toHaveTextContent('2 sent, 3 received');
});
