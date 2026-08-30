import React, { useState } from 'react';
import { fmt$ } from '../../utils/formatting';
import { AlertIcon, CheckIcon } from './icons';

function formatWhen(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d) ? null : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// What the last action managed to write to the spreadsheet. Worth saying out
// loud either way: the whole point of marking a month is that the other person
// sees it on the sheet, so silence would leave that unanswered.
function PublishNote({ published }) {
  if (!published) return null;

  if (published.published) {
    return (
      <span className="sh-publish-note" role="status">
        <CheckIcon size={12} />
        Written to {published.worksheet}
        {published.renamed ? ' — tab marked PIF' : ''}
      </span>
    );
  }
  return (
    <span className="sh-publish-note sh-publish-note--warn" role="status">
      <AlertIcon size={13} />
      Saved here, but the sheet wasn&apos;t updated
      {published.reason ? `: ${published.reason}` : '.'}
    </span>
  );
}

// Settling is advisory: either side may declare a month paid, so nothing here
// waits on the peer. The peer's position is reported alongside — never as a
// gate on the buttons.
export default function SettleActions({
  state,
  peerName,
  busy,
  published,
  onReady,
  onWithdrawReady,
  onPaid,
  onReopen,
}) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState('');

  if (!state) return null;

  const settled = state.state === 'settled';
  const paidWhen = formatWhen(state.paid_at);

  const confirmPaid = async () => {
    await onPaid(note);
    setNote('');
    setNoteOpen(false);
  };

  if (settled) {
    return (
      <div className="sh-settle-actions sh-settle-actions--done" data-testid="settle-actions">
        <span className="sh-settled-badge">
          <CheckIcon size={13} />
          Paid in full
          {paidWhen ? ` · ${paidWhen}` : ''}
        </span>
        <span className="sh-settled-who">
          {state.paid_by_me
            ? 'You marked this month settled.'
            : `${state.paid_by_name || peerName} marked this month settled.`}
          {state.paid_note ? ` “${state.paid_note}”` : ''}
        </span>
        {state.paid_by_me ? (
          <button type="button" className="sh-mini" onClick={onReopen} disabled={busy}>
            Reopen
          </button>
        ) : (
          // Only the instance that declared it can take it back; ours would
          // clear a record we never wrote.
          <span className="sh-settled-hint">
            Only {state.paid_by_name || peerName} can reopen it.
          </span>
        )}
        <PublishNote published={published} />
      </div>
    );
  }

  return (
    <div className="sh-settle-actions" data-testid="settle-actions">
      {state.net_disagreement && (
        <span className="sh-settle-warn" role="alert">
          <AlertIcon size={14} />
          You and {peerName} don&apos;t agree on the net — you have{' '}
          {fmt$(Math.abs(state.net_disagreement.mine))}, they have{' '}
          {fmt$(Math.abs(state.net_disagreement.theirs))}. Sync, or check for a
          row only one of you has.
        </span>
      )}

      <span className="sh-settle-ready">
        {state.you_ready ? (
          <>
            <CheckIcon size={13} />
            You marked your rows complete.
            <button type="button" className="sh-linkish" onClick={onWithdrawReady} disabled={busy}>
              Undo
            </button>
          </>
        ) : (
          <button type="button" className="sh-mini" onClick={onReady} disabled={busy}>
            My rows are complete
          </button>
        )}
        <span className="sh-settle-peer">
          {state.peer_ready
            ? `${state.peer_ready_name || peerName} is ready too.`
            : `Waiting on ${peerName}.`}
        </span>
      </span>

      {noteOpen ? (
        <span className="sh-paid-form">
          <label className="sh-paid-label" htmlFor="settle-note">
            How was it settled? (optional)
          </label>
          <input
            id="settle-note"
            className="sh-paid-input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Venmo, 3 Jul"
          />
          <button
            type="button"
            className="sh-mini sh-mini--go"
            onClick={confirmPaid}
            disabled={busy}
          >
            {busy ? 'Saving…' : 'Mark paid'}
          </button>
          <button
            type="button"
            className="sh-mini"
            onClick={() => setNoteOpen(false)}
            disabled={busy}
          >
            Cancel
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="sh-btn sh-btn--primary"
          onClick={() => setNoteOpen(true)}
          disabled={busy}
        >
          Mark paid in full
        </button>
      )}

      <PublishNote published={published} />
    </div>
  );
}
