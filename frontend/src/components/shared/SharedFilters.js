import React from 'react';

export const FILTERS = ['all', 'mine', 'peer', 'attention'];

export function needsAttention(row) {
  return row.dispute_flag === 'Y' || row.publishable === false;
}

export function matchesFilter(row, filter) {
  if (filter === 'mine') return row.owner === 'me';
  if (filter === 'peer') return row.owner === 'peer';
  if (filter === 'attention') return needsAttention(row);
  return true;
}

export default function SharedFilters({ rows, value, onChange, peerName }) {
  const labels = {
    all: 'All',
    mine: 'Yours',
    peer: `${peerName}'s`,
    attention: 'Needs attention',
  };

  return (
    <div className="sh-chips" role="group" aria-label="Filter shared expenses">
      {FILTERS.map((key) => {
        const count = rows.filter((r) => matchesFilter(r, key)).length;
        if (key === 'attention' && count === 0) return null;
        const on = value === key;
        const warn = key === 'attention' && !on;
        return (
          <button
            key={key}
            type="button"
            className={`sh-chip${on ? ' sh-chip--on' : ''}${warn ? ' sh-chip--warn' : ''}`}
            aria-pressed={on}
            onClick={() => onChange(key)}
          >
            {labels[key]} <span className="sh-n">{count}</span>
          </button>
        );
      })}
      <span className="sh-spacer" />
    </div>
  );
}
