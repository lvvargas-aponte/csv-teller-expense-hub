import React from 'react';
import { fmt$, fmtDate } from '../../utils/formatting';

function formatOwesCell(value) {
  return value === null || value === undefined ? '—' : fmt$(value);
}

export default function SharedRow({ row }) {
  const isMe = row.owner === 'me';
  const rowClass = `shared-row${row.publishable === false ? ' shared-row--blocked' : ''}`;

  return (
    <tr className={rowClass}>
      <td className="shared-td-owner">
        <span
          className={`shared-owner-dot${isMe ? ' shared-owner-dot--me' : ' shared-owner-dot--peer'}`}
          aria-hidden="true"
        >
          {isMe ? '●' : '○'}
        </span>
        <span className="shared-owner-name">{row.owner_name}</span>
      </td>
      <td className="shared-td-date">{fmtDate(row.date)}</td>
      <td className="shared-td-desc">
        {row.description}
        {row.dispute_flag && (
          <span
            className="shared-flag shared-flag--dispute"
            title={`Disputed by ${row.dispute_by}: ${row.dispute_note}`}
          >
            ⚑ disputed — {row.dispute_by}: {row.dispute_note}
          </span>
        )}
        {row.publishable === false && (
          <span className="shared-flag shared-flag--blocked" title={row.blocked_reason}>
            ⚠ {row.blocked_reason}
          </span>
        )}
      </td>
      <td className="shared-td-amt">{fmt$(row.amount)}</td>
      <td className="shared-td-amt">{formatOwesCell(row.you_owe)}</td>
    </tr>
  );
}
