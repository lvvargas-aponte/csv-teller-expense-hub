import React, { useMemo } from 'react';
import TxnRow from './TxnRow';
import NoteExpandRow from './NoteExpandRow';
import SplitAdjustRow from './SplitAdjustRow';
import TransferExpandRow from './TransferExpandRow';
import IconLegend from './IconLegend';

const BASE_COL_COUNT = 7;

export default function TransactionTable({
  txns,
  loading,
  selected,
  allVisibleSelected,
  otherPersonName,
  activeExpand,
  onToggle,
  onToggleAll,
  onSplitChange,
  onToggleType,
  onOpenNote,
  onOpenAdj,
  onOpenTransfer,
  onSaveNote,
  onSaveAdj,
  onSaveTransfer,
  onCloseExpand,
  editableCategory = false,
  categories = [],
  onCategoryChange,
  onRemoveCategory,
  onToggleReviewed,
  manualAccountsById = null,
}) {
  const colCount = BASE_COL_COUNT + (editableCategory ? 1 : 0);
  const accountLabelById = useMemo(() => {
    if (!manualAccountsById) return null;
    const map = {};
    Object.values(manualAccountsById).forEach((a) => {
      map[a.id] = a.institution ? `${a.institution} · ${a.name}` : a.name;
    });
    return map;
  }, [manualAccountsById]);
  return (
    <div className="tx-table-card">
      <table className="tx-table">
        <thead>
          <tr>
            <th className="tx-col-cb">
              <input
                type="checkbox"
                className="tx-table-cb"
                aria-label="Select all visible"
                checked={!!allVisibleSelected}
                onChange={onToggleAll}
              />
            </th>
            <th>Date</th>
            <th>Description</th>
            {editableCategory && <th className="tx-col-category">Category</th>}
            <th className="tx-col-amt">Amount</th>
            <th className="tx-col-source">Source</th>
            <th className="tx-col-split">Split</th>
            <th className="tx-col-actions" aria-label="Row actions" style={{ textAlign: 'right' }}>
              <IconLegend />
            </th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={colCount}>
              <div className="tx-empty"><div style={{ fontSize: 28 }}>⏳</div><p>Loading…</p></div>
            </td></tr>
          ) : txns.length === 0 ? (
            <tr><td colSpan={colCount}>
              <div className="tx-empty">
                <div style={{ fontSize: 28 }}>🔍</div>
                <p>No transactions match your filters.</p>
              </div>
            </td></tr>
          ) : (
            txns.map((txn) => {
              const expandNote     = activeExpand === `note-${txn.id}`;
              const expandAdj      = activeExpand === `adj-${txn.id}`;
              const expandTransfer = activeExpand === `transfer-${txn.id}`;
              const transferTargetName = txn.transfer_to_account_id
                ? (accountLabelById?.[txn.transfer_to_account_id] || null)
                : null;
              return (
                <React.Fragment key={txn.id}>
                  <TxnRow
                    txn={txn}
                    otherPersonName={otherPersonName}
                    isSelected={selected.has(txn.id)}
                    onToggle={onToggle}
                    onSplitChange={onSplitChange}
                    onToggleType={onToggleType}
                    onOpenNote={onOpenNote}
                    onOpenAdj={onOpenAdj}
                    onOpenTransfer={onOpenTransfer}
                    expandNote={expandNote}
                    expandAdj={expandAdj}
                    expandTransfer={expandTransfer}
                    transferTargetName={transferTargetName}
                    editableCategory={editableCategory}
                    categories={categories}
                    onCategoryChange={onCategoryChange}
                    onRemoveCategory={onRemoveCategory}
                    onToggleReviewed={onToggleReviewed}
                  />
                  {expandNote && (
                    <NoteExpandRow
                      txn={txn}
                      colSpan={colCount}
                      onSave={(notes) => onSaveNote(txn, notes)}
                      onClose={onCloseExpand}
                    />
                  )}
                  {expandAdj && (
                    <SplitAdjustRow
                      txn={txn}
                      otherPersonName={otherPersonName}
                      colSpan={colCount}
                      onSave={(amounts) => onSaveAdj(txn, amounts)}
                      onClose={onCloseExpand}
                    />
                  )}
                  {expandTransfer && (
                    <TransferExpandRow
                      txn={txn}
                      colSpan={colCount}
                      onSave={(accountId) => onSaveTransfer(txn, accountId)}
                      onClose={onCloseExpand}
                    />
                  )}
                </React.Fragment>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
