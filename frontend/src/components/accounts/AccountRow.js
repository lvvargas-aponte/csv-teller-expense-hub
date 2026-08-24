import React from 'react';
import Spin from '../ui/Spin';
import { formatAccountType } from '../../utils/formatting';

function statusChipFor(acct, isManual) {
  if (isManual) return { label: 'Manual', bg: '#1e293b', color: '#94a3b8' };
  if (acct._connection_error) {
    return acct._error_status === 429
      ? { label: 'Rate Limited',     bg: '#422006', color: '#fbbf24' }
      : { label: 'Connection Error', bg: '#450a0a', color: '#fca5a5' };
  }
  if (acct.status === 'closed') return { label: 'Closed', bg: '#1f2937', color: '#9ca3af' };
  return { label: 'Active', bg: '#052e16', color: '#86efac' };
}

/**
 * One account inside a group. The institution lives on the group heading, so
 * the row leads with the account name.
 */
export default function AccountRow({
  acct, institution, isConfirming, isDeleting, onConfirm, onCancelConfirm, onDisconnect, onPurge,
}) {
  // Manual accounts have no upstream connection, so "Disconnect" doesn't
  // apply — permanent delete is the only action.
  const isManual = acct._source === 'manual';
  const subtype  = formatAccountType(acct.subtype || acct.type || '');
  const chip     = statusChipFor(acct, isManual);

  const purgeBtn = (
    <button type="button" className="btn btn-sm account-row-danger"
            disabled={isDeleting}
            title="Permanently delete this account and all its local data"
            onClick={() => onPurge({ id: acct.id, label: `${institution} · ${acct.name}` })}>
      {isDeleting ? <Spin /> : null} Delete permanently
    </button>
  );

  return (
    <div className="account-row">
      <div className="account-row-info">
        <div className="account-row-name">
          {acct.name}
          <span className="account-chip" style={{ background: chip.bg, color: chip.color }}>
            {chip.label}
          </span>
        </div>
        {subtype && <div className="account-row-sub">{subtype}</div>}
      </div>

      <div className="account-row-actions">
        {isManual ? purgeBtn : isConfirming ? (
          <>
            <span className="account-row-confirm-label">Disconnect? Local data stays.</span>
            <button type="button" className="btn btn-sm account-row-confirm-yes"
                    onClick={() => onDisconnect(acct.id)}>
              Yes
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onCancelConfirm}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-secondary btn-sm"
                    disabled={isDeleting}
                    onClick={() => onConfirm(acct.id)}>
              {isDeleting ? <Spin /> : '🗑️'} Disconnect
            </button>
            {/* A failed connection has no local record worth purging yet. */}
            {!acct._connection_error && purgeBtn}
          </>
        )}
      </div>
    </div>
  );
}
