import React, { useState } from 'react';
import { fmt$, fmtDate, channelLabel, CHANNEL_COLOR, formatAccountType } from '../utils/formatting';

export default function TxnRow({ txn, otherPersonName, isSelected, onToggle, onQuickMark, onEdit, onNote }) {
  const [marking, setMarking] = useState(false);

  const handleMark = async (isShared) => {
    setMarking(true);
    try { await onQuickMark(txn, isShared); } finally { setMarking(false); }
  };

  const rowClass = [
    'txn-row',
    isSelected   ? 'txn-row--selected' : '',
    txn.is_shared ? 'txn-row--shared'  : '',
  ].filter(Boolean).join(' ');

  return (
    <tr className={rowClass}>
      <td>
        <input type="checkbox" checked={isSelected} onChange={() => onToggle(txn.id)} style={{ cursor: 'pointer' }} />
      </td>
      <td className="td-date">{fmtDate(txn.date)}</td>
      <td>
        <div className="txn-desc">{txn.description}</div>
      </td>
      <td className="td-amount">
        {fmt$(txn.amount)}
        <span
          className={`txn-type-badge txn-type-badge--${txn.transaction_type || 'debit'}`}
          title={txn.transaction_type === 'credit' ? 'Credit – money in (refund, payment received)' : 'Debit – money out (purchase, payment made)'}
        >
          {txn.transaction_type === 'credit' ? 'CR' : 'DR'}
        </span>
      </td>
      <td>
        <div>{txn.institution || '—'}</div>
        {txn.account_type && (
          <div className="account-type-label">{formatAccountType(txn.account_type)}</div>
        )}
        <span className="badge" style={{ background: CHANNEL_COLOR[channelLabel(txn.source)] || '#6b7280' }}>
          {channelLabel(txn.source)}
        </span>
      </td>
      <td>
        {txn.is_shared ? (
          <div className="split-info">
            <span className="badge-shared">shared</span>
            <div className="split-detail">
              {otherPersonName} owes {fmt$(txn.person_2_owes || 0)}
            </div>
          </div>
        ) : (
          <span className="badge-personal">personal</span>
        )}
      </td>
      <td>
        <div className="action-group">
          <div className="toggle-group">
            <button
              type="button"
              disabled={marking || !txn.is_shared}
              onClick={() => handleMark(false)}
              className={`toggle-btn${!txn.is_shared ? ' toggle-btn--personal' : ''}`}
            >
              Personal
            </button>
            <button
              type="button"
              disabled={marking || txn.is_shared}
              onClick={() => handleMark(true)}
              className={`toggle-btn${txn.is_shared ? ' toggle-btn--shared' : ''}`}
            >
              50/50
            </button>
          </div>
          <button type="button" className="icon-btn" title="Adjust split" onClick={onEdit}>🧮</button>
          <button type="button" className="icon-btn" title={txn.notes || 'Add note'} onClick={onNote}>
            {txn.notes ? '📝' : '🗒️'}
          </button>
        </div>
      </td>
    </tr>
  );
}
