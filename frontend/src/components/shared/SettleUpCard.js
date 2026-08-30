import React from 'react';
import { fmt$ } from '../../utils/formatting';

function pct(value, max) {
  return max > 0 ? `${Math.round((value / max) * 100)}%` : '0%';
}

export default function SettleUpCard({ settlement, peerName, monthLabel }) {
  if (!settlement) return null;

  const {
    you_owe_total: youOwe,
    they_owe_total: theyOwe,
    net,
    direction,
    counted_count: countedCount,
    counted_amount: countedAmount,
    blocked_count: blockedCount,
  } = settlement;

  const netClass = direction === 'they_owe'
    ? ''
    : direction === 'you_owe' ? ' sh-net-amt--out' : ' sh-net-amt--even';

  const caption = direction === 'they_owe'
    ? `${peerName} owes you, net for ${monthLabel}.`
    : direction === 'you_owe'
      ? `You owe ${peerName}, net for ${monthLabel}.`
      : `You're even for ${monthLabel}.`;

  const max = Math.max(youOwe, theyOwe);

  return (
    <div className="sh-settle" data-testid="settle-up">
      <div className="sh-settle-net">
        <span className="sh-eyebrow">Settle up</span>
        <span className={`sh-net-amt${netClass}`} data-testid="settle-net">{fmt$(net)}</span>
        <span className="sh-net-sub">
          {caption}<br />Updates as shared expenses are added.
        </span>
      </div>

      {max > 0 && (
        <div className="sh-settle-bars">
          <div className="sh-bar-row">
            <div className="sh-bar-top">
              <span className="sh-who">{peerName} owes you</span>
              <span className="sh-val">{fmt$(theyOwe)}</span>
            </div>
            <div className="sh-track"><div className="sh-fill" style={{ width: pct(theyOwe, max) }} /></div>
          </div>
          <div className="sh-bar-row">
            <div className="sh-bar-top">
              <span className="sh-who">You owe {peerName}</span>
              <span className="sh-val">{fmt$(youOwe)}</span>
            </div>
            <div className="sh-track"><div className="sh-fill sh-fill--peer" style={{ width: pct(youOwe, max) }} /></div>
          </div>
        </div>
      )}

      {(countedCount > 0 || blockedCount > 0) && (
        <div className="sh-settle-side">
          {countedCount > 0 && (
            <div className="sh-stat">
              <b>{countedCount} shared expense{countedCount === 1 ? '' : 's'}</b>
              <span>{fmt$(countedAmount)} counted this month</span>
            </div>
          )}
          {blockedCount > 0 && (
            <div className="sh-stat">
              <b>{blockedCount} not counted</b>
              <span>can&apos;t be published yet</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
