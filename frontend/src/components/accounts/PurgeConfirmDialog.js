import React, { useState } from 'react';
import Spin from '../ui/Spin';
import { Z_BACKDROP_PANEL } from '../../utils/zIndex';

export const PURGE_CONFIRM_WORD = 'delete';

/** Type-to-confirm gate for the irreversible delete. */
export default function PurgeConfirmDialog({ target, busy, onCancel, onConfirm }) {
  const [text, setText] = useState('');
  const matches = text.trim().toLowerCase() === PURGE_CONFIRM_WORD;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm permanent account deletion"
      className="purge-backdrop"
      style={{ zIndex: Z_BACKDROP_PANEL + 1 }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Delete account permanently?</div>
            <div className="modal-sub">{target.label}</div>
          </div>
        </div>
        <div className="modal-body purge-body">
          <p style={{ marginTop: 0 }}>
            This will remove the account everywhere — its balance, snapshots,
            and APR / credit-limit details. Linked transactions stay but lose
            their account reference.
          </p>
          <p>
            To confirm, type <code className="purge-word">{PURGE_CONFIRM_WORD}</code> below.
          </p>
          <label htmlFor="purge-confirm" className="sr-only">Type delete to confirm</label>
          <input
            id="purge-confirm"
            type="text"
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={PURGE_CONFIRM_WORD}
            disabled={busy}
            className="form-input purge-input"
          />
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn btn-sm purge-go${matches ? ' purge-go--armed' : ''}`}
            disabled={!matches || busy}
            onClick={onConfirm}
          >
            {busy ? <><Spin /> Deleting…</> : 'Delete forever'}
          </button>
        </div>
      </div>
    </div>
  );
}
