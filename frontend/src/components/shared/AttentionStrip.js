import React from 'react';
import { AlertIcon } from './icons';

function phrases(disputedByPeer, disputedByYou, blocked, peerName) {
  const out = [];
  if (disputedByPeer) {
    out.push(`${peerName} disputed ${disputedByPeer === 1 ? 'one expense' : `${disputedByPeer} expenses`}`);
  }
  if (disputedByYou) {
    out.push(`you disputed ${disputedByYou === 1 ? 'one expense' : `${disputedByYou} expenses`}`);
  }
  if (blocked) {
    out.push(blocked === 1
      ? "one can't be published until it's fixed"
      : `${blocked} can't be published until they're fixed`);
  }
  // Each phrase is written lowercase so it can be joined mid-sentence; the
  // result is a sentence of its own, so the leading one gets a capital.
  const sentence = out.join(', and ');
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

export default function AttentionStrip({ rows, peerName, onReview }) {
  const disputedByPeer = rows.filter((r) => r.owner === 'me' && r.dispute_flag === 'Y').length;
  const disputedByYou = rows.filter((r) => r.owner === 'peer' && r.dispute_flag === 'Y').length;
  const blocked = rows.filter((r) => r.publishable === false).length;
  const total = disputedByPeer + disputedByYou + blocked;

  if (total === 0) return null;

  return (
    <div className="sh-attn" data-testid="attention-strip">
      <span className="sh-attn-icon"><AlertIcon size={16} /></span>
      <span className="sh-attn-text">
        <b>{total} row{total === 1 ? '' : 's'} need{total === 1 ? 's' : ''} you.</b>{' '}
        {phrases(disputedByPeer, disputedByYou, blocked, peerName)}.
      </span>
      <button type="button" className="sh-btn" onClick={onReview}>Review</button>
    </div>
  );
}
