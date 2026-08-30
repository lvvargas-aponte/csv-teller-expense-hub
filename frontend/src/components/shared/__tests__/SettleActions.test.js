import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettleActions from '../SettleActions';

const PEER = 'Christy';

function state(overrides = {}) {
  return {
    state: 'open',
    period: '2026-06',
    you_ready: false,
    peer_ready: false,
    peer_ready_name: null,
    paid_at: null,
    paid_note: null,
    paid_by_me: false,
    paid_by_name: null,
    declared_net: null,
    live_net: 56.13,
    net_disagreement: null,
    ...overrides,
  };
}

const renderActions = (overrides = {}, handlers = {}) =>
  render(
    <SettleActions
      state={state(overrides)}
      peerName={PEER}
      busy={false}
      onReady={jest.fn()}
      onWithdrawReady={jest.fn()}
      onPaid={jest.fn()}
      onReopen={jest.fn()}
      {...handlers}
    />,
  );

test('renders nothing before the settlement state has loaded', () => {
  const { container } = render(<SettleActions state={null} peerName={PEER} />);
  expect(container).toBeEmptyDOMElement();
});

test('an open month offers to mark your rows complete and says who it waits on', () => {
  renderActions();

  expect(screen.getByRole('button', { name: /my rows are complete/i })).toBeInTheDocument();
  expect(screen.getByText(`Waiting on ${PEER}.`)).toBeInTheDocument();
});

test('once you are ready it says so and offers to undo', async () => {
  const onWithdrawReady = jest.fn();
  renderActions({ state: 'ready', you_ready: true }, { onWithdrawReady });

  expect(screen.getByText(/you marked your rows complete/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /undo/i }));
  expect(onWithdrawReady).toHaveBeenCalled();
});

test('the peer being ready is reported without gating anything', () => {
  renderActions({ peer_ready: true, peer_ready_name: PEER });

  expect(screen.getByText(`${PEER} is ready too.`)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /mark paid in full/i })).toBeEnabled();
});

test('marking paid is offered even when neither side has declared ready', () => {
  // Settlement is advisory — the person who moved the money decides.
  renderActions({ you_ready: false, peer_ready: false });

  expect(screen.getByRole('button', { name: /mark paid in full/i })).toBeEnabled();
});

test('a net disagreement is surfaced but never blocks marking paid', () => {
  renderActions({
    you_ready: true,
    peer_ready: true,
    net_disagreement: { mine: 56.13, theirs: 40 },
  });

  const warning = screen.getByRole('alert');
  expect(warning).toHaveTextContent(/don't agree on the net/i);
  expect(warning).toHaveTextContent('$56.13');
  expect(warning).toHaveTextContent('$40.00');
  expect(screen.getByRole('button', { name: /mark paid in full/i })).toBeEnabled();
});

test('marking paid collects an optional note and passes it on', async () => {
  const onPaid = jest.fn().mockResolvedValue(undefined);
  renderActions({}, { onPaid });

  await userEvent.click(screen.getByRole('button', { name: /mark paid in full/i }));
  await userEvent.type(screen.getByLabelText(/how was it settled/i), 'Venmo, 3 Jul');
  await userEvent.click(screen.getByRole('button', { name: /^mark paid$/i }));

  expect(onPaid).toHaveBeenCalledWith('Venmo, 3 Jul');
});

test('cancelling the note form does not settle the month', async () => {
  const onPaid = jest.fn();
  renderActions({}, { onPaid });

  await userEvent.click(screen.getByRole('button', { name: /mark paid in full/i }));
  await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

  expect(onPaid).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: /mark paid in full/i })).toBeInTheDocument();
});

test('a month you settled shows the badge, your note, and a way back', async () => {
  const onReopen = jest.fn();
  renderActions({
    state: 'settled',
    paid_at: '2026-07-03T12:00:00Z',
    paid_note: 'Venmo',
    paid_by_me: true,
  }, { onReopen });

  expect(screen.getByText(/paid in full/i)).toBeInTheDocument();
  expect(screen.getByText(/you marked this month settled/i)).toHaveTextContent('Venmo');

  await userEvent.click(screen.getByRole('button', { name: /reopen/i }));
  expect(onReopen).toHaveBeenCalled();
});

test('a month the peer settled names them and offers no reopen button', () => {
  renderActions({
    state: 'settled',
    paid_at: '2026-07-03T12:00:00Z',
    paid_by_me: false,
    paid_by_name: PEER,
  });

  expect(screen.getByText(`${PEER} marked this month settled.`)).toBeInTheDocument();
  // Reopening clears the record that declared it, and that record is theirs.
  expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument();
  expect(screen.getByText(`Only ${PEER} can reopen it.`)).toBeInTheDocument();
});

test('every control is disabled while a settlement call is in flight', () => {
  render(
    <SettleActions
      state={state({ you_ready: true })}
      peerName={PEER}
      busy
      onReady={jest.fn()}
      onWithdrawReady={jest.fn()}
      onPaid={jest.fn()}
      onReopen={jest.fn()}
    />,
  );

  expect(screen.getByRole('button', { name: /undo/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /mark paid in full/i })).toBeDisabled();
});

describe('what reached the spreadsheet', () => {
  test('a successful publish names the worksheet it wrote to', () => {
    render(
      <SettleActions
        state={state({ you_ready: true })}
        peerName={PEER}
        busy={false}
        published={{ published: true, worksheet: 'June 2026' }}
        onReady={jest.fn()}
        onWithdrawReady={jest.fn()}
        onPaid={jest.fn()}
        onReopen={jest.fn()}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Written to June 2026');
  });

  test('settling reports the tab rename too', () => {
    render(
      <SettleActions
        state={state({ state: 'settled', paid_at: '2026-07-03T12:00:00Z', paid_by_me: true })}
        peerName={PEER}
        busy={false}
        published={{ published: true, worksheet: 'June 2026 - PIF', renamed: 'June 2026 - PIF' }}
        onReady={jest.fn()}
        onWithdrawReady={jest.fn()}
        onPaid={jest.fn()}
        onReopen={jest.fn()}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('tab marked PIF');
  });

  test('a failed publish says the record was kept locally, and why', () => {
    // The local record still stands — only the sheet write failed — so the
    // wording must not read as "nothing happened".
    render(
      <SettleActions
        state={state({ you_ready: true })}
        peerName={PEER}
        busy={false}
        published={{ published: false, reason: 'No worksheet for 2026-06 yet.' }}
        onReady={jest.fn()}
        onWithdrawReady={jest.fn()}
        onPaid={jest.fn()}
        onReopen={jest.fn()}
      />,
    );

    const note = screen.getByRole('status');
    expect(note).toHaveTextContent(/saved here, but the sheet wasn't updated/i);
    expect(note).toHaveTextContent('No worksheet for 2026-06 yet.');
  });

  test('nothing is claimed when no action has run yet', () => {
    render(
      <SettleActions
        state={state()}
        peerName={PEER}
        busy={false}
        published={null}
        onReady={jest.fn()}
        onWithdrawReady={jest.fn()}
        onPaid={jest.fn()}
        onReopen={jest.fn()}
      />,
    );

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
