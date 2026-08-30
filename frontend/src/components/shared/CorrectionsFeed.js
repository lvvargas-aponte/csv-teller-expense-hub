import React from 'react';
import { AlertIcon } from './icons';

export default function CorrectionsFeed({ corrections, onDismiss }) {
  if (!corrections || corrections.length === 0) return null;

  return (
    <div className="sh-corrections">
      {corrections.map((c) => (
        <div key={c.id} className="sh-corr" role="alert">
          <span className="sh-attn-icon"><AlertIcon /></span>
          <span className="sh-corr-text">
            <b>{c.column_name}</b> on {c.txn_id} — the sheet said <b>{c.sheet_value}</b>;
            {' '}this app rewrote it to <b>{c.app_value}</b>.
          </span>
          <button
            type="button"
            className="sh-mini"
            onClick={() => onDismiss(c.id)}
            aria-label={`Dismiss correction for ${c.column_name} on ${c.txn_id}`}
          >Dismiss</button>
        </div>
      ))}
    </div>
  );
}
