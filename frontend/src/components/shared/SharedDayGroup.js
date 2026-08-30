import React from 'react';
import SharedRow from './SharedRow';
import { fmt$, fmtDate } from '../../utils/formatting';

function dayLabel(value) {
  const d = new Date(`${value}T00:00:00`);
  return isNaN(d)
    ? fmtDate(value)
    : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

export default function SharedDayGroup({
  date, rows, peerName, personNames, mySlot, onDispute, onFix,
}) {
  const total = rows.reduce((sum, r) => sum + Math.abs(parseFloat(r.amount) || 0), 0);

  return (
    <div className="sh-daygroup" data-testid={`day-group-${date}`}>
      <div className="sh-dayhead">
        <span className="sh-d">{dayLabel(date)}</span>
        <span className="sh-t">
          {rows.length} expense{rows.length === 1 ? '' : 's'} · {fmt$(total)}
        </span>
      </div>
      {rows.map((row) => (
        <SharedRow
          key={row.transaction_id}
          row={row}
          peerName={peerName}
          personNames={personNames}
          mySlot={mySlot}
          onDispute={onDispute}
          onFix={onFix}
        />
      ))}
    </div>
  );
}
