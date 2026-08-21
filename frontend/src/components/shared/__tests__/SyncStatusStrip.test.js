import React from 'react';
import { render, screen } from '@testing-library/react';
import SyncStatusStrip from '../SyncStatusStrip';

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
  const { container } = render(<SyncStatusStrip status={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('a successful last run shows success and the sent/received counts', () => {
  render(<SyncStatusStrip status={status()} />);

  expect(screen.getByText(/success/i)).toBeInTheDocument();
  expect(screen.getByText(/2 sent, 3 received/)).toBeInTheDocument();
});

test('a refusal renders the readable message, not the raw reason code', () => {
  render(<SyncStatusStrip status={status({
    refusal: {
      reason: 'contract_version',
      message: 'Sync refused: the two instances speak different versions of the sheet contract.',
    },
  })} />);

  const refusal = screen.getByRole('alert');
  expect(refusal).toHaveTextContent(/two instances speak different versions/);
  expect(refusal).not.toHaveTextContent(/Sync refused — contract_version/);
});
