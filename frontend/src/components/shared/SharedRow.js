import React, { useState } from 'react';
import { fmt$, formatCategory } from '../../utils/formatting';
import { AlertIcon, FlagIcon } from './icons';
import FixBlockedRow from './FixBlockedRow';

function initial(name) {
  return (name || '?').trim().charAt(0).toUpperCase() || '?';
}

export default function SharedRow({ row, peerName, personNames, mySlot, onDispute, onFix }) {
  const isMe = row.owner === 'me';
  const hasDispute = row.dispute_flag === 'Y';
  const isBlocked = row.publishable === false;

  const [formOpen, setFormOpen] = useState(false);
  const [note, setNote] = useState('');
  const [editingFlag, setEditingFlag] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [fixOpen, setFixOpen] = useState(false);

  const openRaise = () => { setNote(''); setEditingFlag(null); setFormOpen(true); };
  const openEdit = () => { setNote(row.dispute_note || ''); setEditingFlag(row.dispute_flag); setFormOpen(true); };
  const cancel = () => setFormOpen(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: editingFlag || 'Y', note });
      setFormOpen(false);
    } catch {
      // error already surfaced by the caller; keep the form open with the note
    } finally {
      setSubmitting(false);
    }
  };

  const withdraw = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: null, note: null });
    } catch {
      // error already surfaced by the caller
    } finally {
      setSubmitting(false);
    }
  };

  // Empty meta is omitted rather than dashed: a peer row has no account or
  // category columns to report, and a dash would read as a missing value.
  const meta = [
    row.account,
    row.category ? formatCategory(row.category) : null,
    row.split_label,
  ].filter(Boolean);

  const rowClass = `sh-row${isBlocked ? ' sh-row--block' : ''}${hasDispute ? ' sh-row--flag' : ''}`;

  return (
    // The row lost its <tr>/<td> when it stopped being a table, so it says out
    // loud what the old column headers used to convey.
    <div
      className={rowClass}
      role="group"
      aria-label={`${row.description}, paid by ${row.owner_name}`}
      data-testid={`shared-row-${row.transaction_id}`}
    >
      <span
        className={`sh-who-chip${isMe ? ' sh-who-chip--me' : ' sh-who-chip--peer'}`}
      >
        <span aria-hidden="true">{initial(row.owner_name)}</span>
        <span className="sh-sr-only">{row.owner_name}</span>
      </span>

      <div className="sh-row-main">
        <span className="sh-desc">{row.description}</span>

        <div className="sh-meta">
          {meta.map((item, i) => (
            <React.Fragment key={`${i}-${item}`}>
              {i > 0 && <span className="sh-b">·</span>}
              <span>{item}</span>
            </React.Fragment>
          ))}
          {hasDispute && (
            <span className="sh-tag sh-tag--flag">
              <FlagIcon />{isMe ? 'Disputed' : 'You disputed'}
            </span>
          )}
          {isBlocked && (
            <span className="sh-tag sh-tag--block">
              <AlertIcon size={10} />Can&apos;t publish
            </span>
          )}
          {isMe && !isBlocked && !row.synced_at && (
            <span className="sh-tag sh-tag--pend">Not synced yet</span>
          )}
        </div>

        {isMe && hasDispute && (
          <div className="sh-note">
            <b>{row.dispute_by} is disputing this</b>
            {row.dispute_note ? <> — {row.dispute_note}</> : null}
          </div>
        )}

        {!isMe && hasDispute && !formOpen && (
          <div className="sh-note">
            <b>You disputed this</b>
            {row.dispute_note ? <> — {row.dispute_note}</> : null}
          </div>
        )}

        {isBlocked && !fixOpen && (
          <div className="sh-note sh-note--block">{row.blocked_reason}</div>
        )}

        {isBlocked && fixOpen && (
          <FixBlockedRow
            row={row}
            peerName={peerName}
            personNames={personNames}
            mySlot={mySlot}
            onSave={async (patch) => {
              await onFix(row, patch);
              setFixOpen(false);
            }}
            onCancel={() => setFixOpen(false)}
          />
        )}

        {!isMe && formOpen && (
          <div className="sh-dform">
            <label htmlFor={`dispute-note-${row.transaction_id}`} className="sh-dform-label">
              Dispute note
            </label>
            <input
              id={`dispute-note-${row.transaction_id}`}
              className="sh-dform-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What's wrong with this one?"
              autoFocus
            />
            <span className="sh-dform-actions">
              <button
                type="button"
                className="sh-mini sh-mini--go"
                onClick={submit}
                disabled={submitting}
              >{submitting ? 'Saving…' : 'Save'}</button>
              <button
                type="button"
                className="sh-mini"
                onClick={cancel}
                disabled={submitting}
              >Cancel</button>
            </span>
          </div>
        )}
      </div>

      <div className="sh-row-amt">
        <span className="sh-sr-only">Amount </span>{fmt$(row.amount)}
      </div>

      <div className="sh-row-owes">
        {isBlocked ? (
          <span className="sh-owes-none">— not counted —</span>
        ) : row.they_owe !== null && row.they_owe !== undefined ? (
          <>
            <span className="sh-owes-l">{peerName} owes you</span>
            <span className="sh-owes-v">{fmt$(row.they_owe)}</span>
          </>
        ) : row.you_owe !== null && row.you_owe !== undefined ? (
          <>
            <span className="sh-owes-l">You owe {peerName}</span>
            <span className="sh-owes-v sh-owes-v--out">{fmt$(row.you_owe)}</span>
          </>
        ) : (
          <span className="sh-owes-none">no split</span>
        )}
      </div>

      <div className="sh-row-act">
        {isMe && isBlocked && !fixOpen && (
          <button
            type="button"
            className="sh-mini sh-mini--fix"
            onClick={() => setFixOpen(true)}
            aria-label={`Fix ${row.description}`}
          >Fix</button>
        )}

        {!isMe && !formOpen && (
          hasDispute ? (
            <>
              <button
                type="button"
                className="sh-mini"
                onClick={openEdit}
                aria-label={`Edit dispute for ${row.description}`}
              >Edit</button>
              <button
                type="button"
                className="sh-mini"
                onClick={withdraw}
                disabled={submitting}
                aria-label={`Withdraw dispute for ${row.description}`}
              >Withdraw</button>
            </>
          ) : (
            <button
              type="button"
              className="sh-mini"
              onClick={openRaise}
              aria-label={`Dispute ${row.description}`}
            >Dispute</button>
          )
        )}
      </div>
    </div>
  );
}
