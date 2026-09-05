import React, { useMemo, useState, useCallback } from 'react';
import TxnRow from './TxnRow';
import NoteExpandRow from './NoteExpandRow';
import SplitAdjustRow from './SplitAdjustRow';
import TransferExpandRow from './TransferExpandRow';
import TransactionDetailRow from './TransactionDetailRow';
import IconLegend from './IconLegend';
import RulePromptRow from './RulePromptRow';

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
  onDelete,
  manualAccountsById = null,
  onOpenDetail,
  detailId = null,
  personNames = {},
  onSaveDetail,
  onCloseDetail,
  onDetailDraftChange,
  rulePrompt = null,
  rulePromptSaving = false,
  onRulePromptConfirm,
  onRulePromptDismiss,
}) {
  const colCount = BASE_COL_COUNT + (editableCategory ? 1 : 0);

  const [sort, setSort] = useState(null); // { key, dir: 'asc'|'desc' } | null
  const cycleSort = useCallback((key) => {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' };
      if (prev.dir === 'asc')         return { key, dir: 'desc' };
      return null;
    });
  }, []);

  const sortedTxns = useMemo(() => {
    if (!sort) return txns;
    const get = (t) => {
      switch (sort.key) {
        case 'date':        return t.date || '';
        case 'description': return (t.description || '').toLowerCase();
        case 'category':    return (t.category || '').toLowerCase();
        case 'amount':      return Number(t.amount) || 0;
        case 'source':      return (t.institution || '').toLowerCase();
        case 'split':       return t.is_shared ? 1 : 0;
        default:            return '';
      }
    };
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...txns].sort((a, b) => {
      const av = get(a); const bv = get(b);
      if (av < bv) return -1 * dir;
      if (av > bv) return  1 * dir;
      return 0;
    });
  }, [txns, sort]);

  const sortArrow = (key) => {
    if (!sort || sort.key !== key) return '';
    return sort.dir === 'asc' ? ' ▲' : ' ▼';
  };
  const Th = ({ sortKey, className, children }) => (
    <th
      className={className}
      onClick={() => cycleSort(sortKey)}
      style={{ cursor: 'pointer', userSelect: 'none' }}
      title="Click to sort"
    >
      {children}{sortArrow(sortKey)}
    </th>
  );

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
            <Th sortKey="date">Date</Th>
            <Th sortKey="description">Description</Th>
            {editableCategory && <Th sortKey="category" className="tx-col-category">Category</Th>}
            <Th sortKey="amount" className="tx-col-amt">Amount</Th>
            <Th sortKey="source" className="tx-col-source">Source</Th>
            <Th sortKey="split" className="tx-col-split">Split</Th>
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
          ) : sortedTxns.length === 0 ? (
            <tr><td colSpan={colCount}>
              <div className="tx-empty">
                <div style={{ fontSize: 28 }}>🔍</div>
                <p>No transactions match your filters.</p>
              </div>
            </td></tr>
          ) : (
            sortedTxns.map((txn) => {
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
                    onDelete={onDelete}
                    onOpenDetail={onOpenDetail}
                    isDetailOpen={txn.id === detailId}
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
                  {rulePrompt?.txnId === txn.id && (
                    <RulePromptRow
                      colSpan={colCount}
                      merchant={rulePrompt.merchant}
                      category={rulePrompt.category}
                      claimable={rulePrompt.claimable}
                      protectedCount={rulePrompt.protected}
                      saving={rulePromptSaving}
                      onConfirm={onRulePromptConfirm}
                      onDismiss={onRulePromptDismiss}
                    />
                  )}
                  {txn.id === detailId && (
                    <TransactionDetailRow
                      txn={txn}
                      colSpan={colCount}
                      personNames={personNames}
                      categories={categories}
                      onSave={onSaveDetail}
                      onRemoveCategory={onRemoveCategory}
                      onDelete={onDelete}
                      onClose={onCloseDetail}
                      onDraftChange={onDetailDraftChange}
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
