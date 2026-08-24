import React from 'react';
import Spin from '../ui/Spin';

/**
 * One SnapTrade brokerage authorization.
 *
 * Rows are connections, not accounts: SnapTrade revokes per authorization, so
 * disconnecting "Robinhood" takes every Robinhood account with it. The count
 * makes that consequence visible before the click.
 */
export default function BrokerageRow({
  conn, accountCount, isConfirming, isDeleting, onConfirm, onCancelConfirm, onDisconnect,
}) {
  const chip = conn.disabled
    ? { label: 'Needs Reconnect', bg: '#450a0a', color: '#fca5a5' }
    : { label: 'Active',          bg: '#052e16', color: '#86efac' };

  return (
    <div className="account-row">
      <div className="account-row-info">
        <div className="account-row-name">
          {conn.brokerage}
          <span className="account-chip" style={{ background: chip.bg, color: chip.color }}>
            {chip.label}
          </span>
        </div>
        <div className="account-row-sub">
          {accountCount === 1 ? '1 account' : `${accountCount} accounts`}
        </div>
      </div>

      <div className="account-row-actions">
        {isConfirming ? (
          <>
            <span className="account-row-confirm-label">
              Disconnect? Reconnect via the brokerage portal.
            </span>
            <button type="button" className="btn btn-sm account-row-confirm-yes"
                    onClick={() => onDisconnect(conn.id)}>
              Yes
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onCancelConfirm}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-secondary btn-sm"
                  disabled={isDeleting}
                  onClick={() => onConfirm(conn.id)}>
            {isDeleting ? <Spin /> : '🗑️'} Disconnect
          </button>
        )}
      </div>
    </div>
  );
}
