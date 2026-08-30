import React, { useState } from 'react';
import { fmt$, fmtDate, channelLabel, isBankChannel, formatCategory, formatAccountType } from '../../utils/formatting';
import SplitPill from './SplitPill';
import CategoryCombobox from './CategoryCombobox';

const CAT_ICONS = {
  restaurants:           '🍽',
  food_and_drink:        '🍽',
  groceries:             '🛒',
  supermarkets:          '🛒',
  shopping:              '🛍',
  merchandise:           '📦',
  travel:                '✈',
  entertainment:         '✈',
  travel_entertainment:  '✈',
  fuel:                  '⛽',
  gas:                   '⛽',
  interest:              '📈',
  payments:              '💳',
  payments_and_credits:  '💳',
};

function catIconFor(cat) {
  if (!cat) return null;
  const key = cat.toLowerCase().replace(/[\s/]+/g, '_').replace(/&/g, 'and');
  return CAT_ICONS[key] || null;
}

function fmtShortDate(s) {
  // Match the design's MM/DD/YY format using DM Mono.
  if (!s) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) return `${m[2]}/${m[3]}/${m[1].slice(2)}`;
  // Fallback — let formatting.fmtDate handle non-ISO dates.
  return fmtDate(s);
}

export default function TxnRow({
  txn,
  otherPersonName,
  isSelected,
  onToggle,
  onSplitChange,
  onToggleType,
  onOpenNote,
  onOpenAdj,
  onOpenTransfer,
  expandNote,
  expandAdj,
  expandTransfer,
  transferTargetName,
  editableCategory = false,
  categories = [],
  onCategoryChange,
  onRemoveCategory,
  onToggleReviewed,
  onDelete,
  onOpenDetail,
  isDetailOpen = false,
}) {
  const [splitting, setSplitting] = useState(false);
  const [flippingType, setFlippingType] = useState(false);

  const isShared = !!txn.is_shared;
  const isCredit = txn.transaction_type === 'credit';
  const sourceLabel = channelLabel(txn.source);
  const sourceClass = isBankChannel(txn.source) ? 'tx-src-badge--bank' : 'tx-src-badge--csv';

  const handleSplit = async (val) => {
    if (splitting) return;
    setSplitting(true);
    try { await onSplitChange(txn, val === 'shared'); } finally { setSplitting(false); }
  };

  const handleToggleType = async () => {
    if (flippingType || !onToggleType) return;
    setFlippingType(true);
    try {
      await onToggleType(txn, isCredit ? 'debit' : 'credit');
    } finally {
      setFlippingType(false);
    }
  };

  const rowClass = [
    'tx-row',
    isSelected   ? 'tx-row--selected' : '',
    isShared     ? 'tx-row--shared'   : '',
    isDetailOpen ? 'tx-row--detail'   : '',
  ].filter(Boolean).join(' ');

  const openDetail = () => onOpenDetail && onOpenDetail(txn.id);
  // Interactive cells keep their own behavior — the row click must not fire behind them.
  const stop = (e) => e.stopPropagation();

  const catIcon  = catIconFor(txn.category);
  const catLabel = txn.category ? formatCategory(txn.category) : '';

  const owedDisplay = isShared ? Number(txn.person_2_owes ?? 0) : 0;

  return (
    <tr className={rowClass} onClick={openDetail}>
      <td className="tx-td-cb" onClick={stop}>
        <input
          type="checkbox"
          aria-label={`Select ${txn.description}`}
          checked={!!isSelected}
          onChange={() => onToggle(txn.id)}
        />
      </td>
      <td className="tx-td-date">{fmtShortDate(txn.date)}</td>
      <td className="tx-td-desc">
        <div className="tx-desc-main" title={txn.description}>
          <button
            type="button"
            className="tx-desc-open"
            aria-label={`Open details for ${txn.description}`}
            onClick={(e) => { stop(e); openDetail(); }}
          >{txn.description}</button>
          {txn.transfer_to_account_id && (
            <span
              className="tx-transfer-chip"
              title={transferTargetName ? `Transfer to ${transferTargetName}` : 'Tagged as internal transfer'}
            >
              → {transferTargetName || 'transfer'}
            </span>
          )}
        </div>
        {!editableCategory && catLabel && (
          <div className="tx-desc-cat">
            {catIcon && <span className="tx-desc-cat-icon" aria-hidden="true">{catIcon}</span>}
            {catLabel}
          </div>
        )}
      </td>
      {editableCategory && (
        <td className="tx-td-category">
          <div className="tx-cat-cell" role="presentation" onClick={stop}>
            {catIcon && <span className="tx-cat-cell-icon" aria-hidden="true">{catIcon}</span>}
            <CategoryCombobox
              value={txn.category || ''}
              categories={categories}
              onChange={(next) => onCategoryChange && onCategoryChange(txn, next)}
              onRemoveCategory={onRemoveCategory}
            />
          </div>
        </td>
      )}
      <td className="tx-td-amount">
        <span className={`tx-amt-val ${isCredit ? 'tx-amt-val--credit' : 'tx-amt-val--debit'}`}>
          {fmt$(txn.amount)}
        </span>
        <button
          type="button"
          onClick={(e) => { stop(e); handleToggleType(); }}
          disabled={flippingType || !onToggleType}
          className={`tx-amt-badge ${isCredit ? 'tx-amt-badge--cr' : 'tx-amt-badge--dr'}`}
          aria-label={`Transaction type: ${isCredit ? 'credit' : 'debit'}. Click to flip.`}
          title={
            (isCredit ? 'Credit – money in' : 'Debit – money out') +
            ' · click to flip'
          }
        >{isCredit ? 'CR' : 'DR'}</button>
      </td>
      <td className="tx-td-source">
        <div className="tx-src-bank">{txn.institution || '—'}</div>
        {txn.account_type && (
          <div className="tx-src-type">{formatAccountType(txn.account_type)}</div>
        )}
        <div className={`tx-src-badge ${sourceClass}`}>{sourceLabel}</div>
      </td>
      <td className="tx-td-split" onClick={stop}>
        <SplitPill
          value={isShared ? 'shared' : 'personal'}
          onChange={handleSplit}
          disabled={splitting}
        />
        {isShared && owedDisplay > 0 && (
          <div className="tx-split-detail">
            {otherPersonName} owes {fmt$(owedDisplay)}
          </div>
        )}
      </td>
      <td className="tx-td-actions" onClick={stop}>
        <div className="tx-row-actions">
          {onToggleReviewed && (
            <button
              type="button"
              className={`tx-act-btn${txn.reviewed ? ' tx-act-btn--active-rev' : ''}`}
              title={txn.reviewed ? 'Reviewed' : 'Mark as reviewed'}
              aria-label={txn.reviewed ? 'Reviewed' : 'Mark as reviewed'}
              aria-pressed={!!txn.reviewed}
              onClick={() => onToggleReviewed(txn, !txn.reviewed)}
            >✓</button>
          )}
          <button
            type="button"
            className={`tx-act-btn${expandAdj ? ' tx-act-btn--active-adj' : ''}`}
            title="Adjust split"
            aria-label="Adjust split"
            onClick={() => onOpenAdj(txn.id)}
          >⚖</button>
          <button
            type="button"
            className={`tx-act-btn${expandNote ? ' tx-act-btn--active-note' : ''}`}
            title={txn.notes || 'Add note'}
            aria-label={txn.notes ? 'Edit note' : 'Add note'}
            onClick={() => onOpenNote(txn.id)}
          >{txn.notes ? '📝' : '✎'}</button>
          {onOpenTransfer && (
            <button
              type="button"
              className={`tx-act-btn${expandTransfer ? ' tx-act-btn--active-note' : ''}${txn.transfer_to_account_id ? ' tx-act-btn--active-rev' : ''}`}
              title={txn.transfer_to_account_id ? `Tagged as transfer${transferTargetName ? ` to ${transferTargetName}` : ''}` : 'Tag as internal transfer'}
              aria-label={txn.transfer_to_account_id
                ? `Edit transfer tag${transferTargetName ? ` (currently → ${transferTargetName})` : ''}`
                : 'Tag as internal transfer'}
              aria-pressed={!!txn.transfer_to_account_id}
              onClick={() => onOpenTransfer(txn.id)}
            >↗</button>
          )}
          {onDelete && (
            <button
              type="button"
              className="tx-act-btn"
              title="Delete transaction"
              aria-label="Delete transaction"
              onClick={() => onDelete(txn)}
            >🗑</button>
          )}
        </div>
      </td>
    </tr>
  );
}
