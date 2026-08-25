import React from 'react';
import Spin from '../ui/Spin';
import { Z_BACKDROP_PANEL } from '../../utils/zIndex';

/**
 * Confirms detaching every account behind one institution.
 *
 * Spells out the blast radius because the row itself only shows a count:
 * the accounts stop syncing, but their transaction history stays — that
 * history is the financial record, and losing it to a connection change
 * would be both surprising and unrecoverable.
 */
export default function RemoveInstitutionDialog({
  institution, accounts, busy, error, onConfirm, onCancel,
}) {
  const n = accounts.length;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Confirm removing ${institution}`}
      className="purge-backdrop"
      style={{ zIndex: Z_BACKDROP_PANEL + 1 }}
      onClick={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
      onKeyDown={(e) => { if (e.key === 'Escape' && !busy) onCancel(); }}
    >
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Remove {institution}?</div>
          </div>
        </div>
        <div className="modal-body">
          <p style={{ marginTop: 0 }}>
            {n === 1
              ? 'This account will stop syncing'
              : `All ${n} accounts will stop syncing`}{' '}
            and drop out of your balances.
          </p>
          {n > 0 && (
            <ul className="set-dialog-list">
              {accounts.map((a) => <li key={a.id}>{a.name}</li>)}
            </ul>
          )}
          <p>
            Past transactions are kept — nothing disappears from your history,
            and reports covering earlier months are unaffected.
          </p>
          {error && <div className="set-inline-error">{error}</div>}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary"
                  disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-sm purge-go purge-go--armed"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? <><Spin /> Removing…</> : 'Remove'}
          </button>
        </div>
      </div>
    </div>
  );
}
