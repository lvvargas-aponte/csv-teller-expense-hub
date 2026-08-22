import React, { useState } from 'react';
import { fmt$, fmtDate } from '../../utils/formatting';

function formatOwesCell(value) {
  return value === null || value === undefined ? '—' : fmt$(value);
}

export default function SharedRow({ row, onDispute }) {
  const isMe = row.owner === 'me';
  const hasDispute = row.dispute_flag === 'Y';
  const isBlocked = row.publishable === false;
  const rowClass = `shared-row${isBlocked ? ' shared-row--blocked' : ''}${hasDispute ? ' shared-row--disputed' : ''}`;

  const [formOpen, setFormOpen] = useState(false);
  const [note, setNote] = useState('');
  const [editingFlag, setEditingFlag] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const openRaise = () => { setNote(''); setEditingFlag(null); setFormOpen(true); };
  const openEdit = () => { setNote(row.dispute_note || ''); setEditingFlag(row.dispute_flag); setFormOpen(true); };
  const cancel = () => setFormOpen(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: editingFlag || 'Y', note });
      setFormOpen(false);
    } catch (e) {
      // error already surfaced by the caller; keep the form open with the note
    } finally {
      setSubmitting(false);
    }
  };

  const withdraw = async () => {
    setSubmitting(true);
    try {
      await onDispute(row.transaction_id, { flag: null, note: null });
    } catch (e) {
      // error already surfaced by the caller
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <tr className={rowClass}>
      <td className="shared-td-owner">
        <span className="shared-owner">
          <span
            className={`shared-owner-dot${isMe ? ' shared-owner-dot--me' : ' shared-owner-dot--peer'}`}
            aria-hidden="true"
          >
            {isMe ? '●' : '○'}
          </span>
          <span className="shared-owner-name">{row.owner_name}</span>
        </span>
      </td>
      <td className="shared-td-date">{fmtDate(row.date)}</td>
      <td className="shared-td-desc">
        <span className="shared-desc-text">{row.description}</span>

        {isMe && hasDispute && (
          <span
            className="shared-note shared-note--dispute"
            title={`${row.dispute_by} is disputing this: ${row.dispute_note}`}
          >
            <span className="shared-note-icon" aria-hidden="true">⚑</span>
            <span className="shared-note-body">
              <strong>{row.dispute_by} is disputing this</strong>
              {row.dispute_note ? <> — {row.dispute_note}</> : null}
            </span>
          </span>
        )}

        {!isMe && hasDispute && !formOpen && (
          <span
            className="shared-note shared-note--dispute"
            title={`You disputed this: ${row.dispute_note}`}
          >
            <span className="shared-note-icon" aria-hidden="true">⚑</span>
            <span className="shared-note-body">
              <strong>You disputed this</strong>
              {row.dispute_note ? <> — {row.dispute_note}</> : null}
            </span>
          </span>
        )}

        {isBlocked && (
          <span className="shared-note shared-note--blocked" title={row.blocked_reason}>
            <span className="shared-note-icon" aria-hidden="true">⚠</span>
            <span className="shared-note-body">{row.blocked_reason}</span>
          </span>
        )}

        {!isMe && formOpen && (
          <span className="shared-dispute-form">
            <label htmlFor={`dispute-note-${row.transaction_id}`} className="shared-dispute-label">
              Dispute note
            </label>
            <input
              id={`dispute-note-${row.transaction_id}`}
              className="shared-dispute-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What's wrong with this one?"
              autoFocus
            />
            <span className="shared-dispute-form-actions">
              <button
                type="button"
                className="shared-dispute-btn shared-dispute-btn--primary"
                onClick={submit}
                disabled={submitting}
              >{submitting ? 'Saving…' : 'Save'}</button>
              <button
                type="button"
                className="shared-dispute-btn"
                onClick={cancel}
                disabled={submitting}
              >Cancel</button>
            </span>
          </span>
        )}
      </td>
      <td className="shared-td-amt">{fmt$(row.amount)}</td>
      <td className="shared-td-amt shared-td-owes">{formatOwesCell(row.you_owe)}</td>
      <td className="shared-td-amt shared-td-owes">{formatOwesCell(row.they_owe)}</td>
      <td className="shared-td-actions">
        {!isMe && !formOpen && (
          hasDispute ? (
            <span className="shared-actions">
              <button
                type="button"
                className="shared-dispute-btn"
                onClick={openEdit}
                aria-label={`Edit dispute for ${row.description}`}
              >Edit</button>
              <button
                type="button"
                className="shared-dispute-btn"
                onClick={withdraw}
                disabled={submitting}
                aria-label={`Withdraw dispute for ${row.description}`}
              >Withdraw</button>
            </span>
          ) : (
            <button
              type="button"
              className="shared-dispute-btn"
              onClick={openRaise}
              aria-label={`Dispute ${row.description}`}
            >Dispute</button>
          )
        )}
      </td>
    </tr>
  );
}
