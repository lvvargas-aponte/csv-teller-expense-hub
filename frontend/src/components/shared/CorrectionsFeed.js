import React from 'react';

export default function CorrectionsFeed({ corrections, onDismiss }) {
  if (!corrections || corrections.length === 0) return null;

  return (
    <div className="shared-corrections">
      {corrections.map((c) => (
        <div key={c.id} className="shared-correction-row" role="alert">
          <span className="shared-correction-icon" aria-hidden="true">⚠</span>
          <span className="shared-correction-text">
            {c.column_name} on {c.txn_id} was {c.sheet_value} on the sheet, rewritten to {c.app_value}
          </span>
          <button
            type="button"
            className="tx-btn tx-btn-secondary shared-correction-dismiss"
            onClick={() => onDismiss(c.id)}
          >
            Dismiss
          </button>
        </div>
      ))}
    </div>
  );
}
