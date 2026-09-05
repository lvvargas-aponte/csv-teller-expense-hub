import React, { useCallback, useState } from 'react';
import axios from 'axios';
import { API_BASE, calculateHalf } from '../../utils/formatting';
import FilterBar from './FilterBar';
import TransactionTable from './TransactionTable';
import BulkBar from './BulkBar';
import SuggestPreviewModal from './SuggestPreviewModal';
import TransactionsRail from './TransactionsRail';
import { useTransactions } from '../../hooks/useTransactions';
import { useFilters } from '../../hooks/useFilters';
import { useCategories } from '../../hooks/useCategories';
import { useSelection } from '../../hooks/useSelection';
import { useTransactionDetail } from '../../hooks/useTransactionDetail';
import Spin from '../ui/Spin';
import {
  deleteTransaction,
  bulkSuggestCategories,
  applyCategoryAssignments,
  previewDuplicates,
  applyDeduplication,
  putTransactionFields,
} from '../../api/transactions';

// Read-mostly view of the full transaction history with inline category
// editing. Reuses the same filter UI as the main transactions screen.
export default function HistoryPage() {
  const {
    transactions, personNames, loading, error, setError, setTransactions, reload,
  } = useTransactions();

  const {
    filterInstitution, setFilterInstitution,
    filterShared, setFilterShared,
    filterMonth, setFilterMonth,
    filterCategory, setFilterCategory,
    search, setSearch,
    availableInstitutions, availableMonths, visible,
  } = useFilters(transactions);

  const {
    selected, toggleSelect, toggleAll, clearSelection,
    sharedSelectedAmt, allVisibleSelected,
  } = useSelection(visible, transactions);

  const {
    categories,
    addLocal: addCategoryLocal,
    remove: removeCategoryRemote,
  } = useCategories();

  const [suggestionPreview, setSuggestionPreview] = useState(null);
  const [suggestingBulk, setSuggestingBulk] = useState(false);
  const [dedupingNow, setDedupingNow] = useState(false);
  const [activeExpand, setActiveExpand] = useState(null);

  const openNote    = useCallback((id) => setActiveExpand(id ? `note-${id}` : null), []);
  const openAdj     = useCallback((id) => setActiveExpand(id ? `adj-${id}`  : null), []);
  const closeExpand = useCallback(() => setActiveExpand(null), []);

  const {
    detailId, detailTxn, detailDraft, setDetailDraft,
    openDetail, closeDetail, saveDetail, applyToSimilar,
  } = useTransactionDetail({
    transactions, setTransactions, setError, addCategoryLocal, listTxns: visible,
  });

  const putTxn = useCallback((txn, patch) => putTransactionFields(txn, patch), []);

  const handleSplitChange = useCallback(async (txn, isShared) => {
    const half = calculateHalf(txn.amount);
    try {
      await putTxn(txn, {
        is_shared: isShared,
        person_1_owes: isShared ? half : 0,
        person_2_owes: isShared ? half : 0,
      });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
        ...t,
        is_shared: isShared,
        person_1_owes: isShared ? half : 0,
        person_2_owes: isShared ? half : 0,
      }));
    } catch {
      setError('Could not update split — please try again.');
    }
  }, [putTxn, setTransactions, setError]);

  const handleToggleType = useCallback(async (txn, nextType) => {
    try {
      await putTxn(txn, { transaction_type: nextType });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
        ...t, transaction_type: nextType,
      }));
    } catch {
      setError('Could not update type — please try again.');
    }
  }, [putTxn, setTransactions, setError]);

  const saveNote = useCallback(async (txn, notes) => {
    try {
      await putTxn(txn, { notes });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : { ...t, notes }));
      setActiveExpand(null);
    } catch {
      setError('Could not save note — please try again.');
    }
  }, [putTxn, setTransactions, setError]);

  const saveAdj = useCallback(async (txn, { person_1_owes, person_2_owes }) => {
    try {
      await putTxn(txn, { is_shared: true, person_1_owes, person_2_owes });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
        ...t, is_shared: true, person_1_owes, person_2_owes,
      }));
      setActiveExpand(null);
    } catch {
      setError('Could not save split — please try again.');
    }
  }, [putTxn, setTransactions, setError]);

  const handleToggleReviewed = useCallback(async (txn, nextReviewed) => {
    try {
      await putTxn(txn, { reviewed: !!nextReviewed });
      setTransactions((prev) => prev.map((t) =>
        t.id !== txn.id ? t : { ...t, reviewed: !!nextReviewed }
      ));
    } catch {
      setError('Could not update reviewed state — please try again.');
    }
  }, [putTxn, setTransactions, setError]);

  const handleCategoryChange = useCallback(async (txn, nextCategory) => {
    const trimmed = (nextCategory || '').trim();
    try {
      await axios.put(`${API_BASE}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared:     !!txn.is_shared,
        who:           txn.who   || '',
        what:          txn.what  || '',
        notes:         txn.notes || '',
        person_1_owes: txn.person_1_owes || 0,
        person_2_owes: txn.person_2_owes || 0,
        reviewed:      !!txn.reviewed,  // category is prep, don't flip reviewed
        category:      trimmed,
      });
      setTransactions((prev) => prev.map((t) =>
        t.id !== txn.id ? t : { ...t, category: trimmed }
      ));
      if (trimmed) addCategoryLocal(trimmed);
    } catch {
      setError('Could not save category — please try again.');
    }
  }, [setTransactions, setError, addCategoryLocal]);

  const handleDelete = useCallback(async (txn) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete this transaction?\n\n${txn.date} · ${txn.description}`)) return;
    try {
      await deleteTransaction(txn.id);
      setTransactions((prev) => prev.filter((t) => t.id !== txn.id));
    } catch {
      setError('Could not delete transaction — please try again.');
    }
  }, [setTransactions, setError]);

  const handleRemoveCategory = useCallback(async (name) => {
    const result = await removeCategoryRemote(name);
    // Refresh transactions so cleared categories disappear from rows.
    await reload();
    return result;
  }, [removeCategoryRemote, reload]);

  const bulkMarkUnreviewed = useCallback(async () => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    try {
      await axios.put(`${API_BASE}/api/transactions/bulk/reviewed`, {
        transaction_ids: ids,
        reviewed: false,
      });
      setTransactions((prev) => prev.map((t) =>
        ids.includes(t.id) ? { ...t, reviewed: false } : t
      ));
      clearSelection();
    } catch {
      setError('Could not unmark as reviewed — please try again.');
    }
  }, [visible, selected, setTransactions, clearSelection, setError]);

  const bulkSuggest = useCallback(async () => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    setSuggestingBulk(true);
    try {
      const r = await bulkSuggestCategories(ids);
      setSuggestionPreview(r.data);
    } catch {
      setError('Could not get category suggestions — please try again');
    } finally {
      setSuggestingBulk(false);
    }
  }, [visible, selected, setError]);

  const handleFindDuplicates = useCallback(async () => {
    setDedupingNow(true);
    try {
      const preview = await previewDuplicates();
      const { duplicate_count: dupes = 0, group_count: groups = 0 } = preview.data || {};
      if (!dupes) {
        // eslint-disable-next-line no-alert
        window.alert('No duplicate transactions found.');
        return;
      }
      // eslint-disable-next-line no-alert
      const ok = window.confirm(
        `Found ${dupes} duplicate transaction${dupes === 1 ? '' : 's'} across `
        + `${groups} group${groups === 1 ? '' : 's'}.\n\n`
        + 'Keep the reviewed/categorized one in each group and remove the rest?'
      );
      if (!ok) return;
      const result = await applyDeduplication();
      await reload();
      // eslint-disable-next-line no-alert
      window.alert(`Removed ${result.data?.removed_count ?? 0} duplicate transactions.`);
    } catch {
      setError('Could not run duplicate cleanup — please try again.');
    } finally {
      setDedupingNow(false);
    }
  }, [reload, setError]);

  const applySuggestions = useCallback(async (items) => {
    try {
      await applyCategoryAssignments(items);
      setSuggestionPreview(null);
      clearSelection();
      await reload();
    } catch {
      setError('Could not apply categories — please try again');
    }
  }, [reload, clearSelection, setError]);

  return (
    <div className="tx-layout">
      <main className="tx-page-wrap">
        <div className="tx-history-header">
          <div className="tx-history-heading-row">
            <h2 className="tx-history-title">Transaction History</h2>
            <button
              type="button"
              className="tx-btn tx-btn-secondary"
              onClick={handleFindDuplicates}
              disabled={dedupingNow}
              title="Find and remove duplicate transactions"
            >
              {dedupingNow ? <><Spin /> Checking…</> : <>⎘ Find duplicates</>}
            </button>
          </div>
          <p className="tx-history-sub">
            Review past transactions and adjust their categories. Type a new name to add one;
            use the ⋯ menu next to a category to remove it. Select rows and click ✨ Suggest
            to ask the local AI for category suggestions.
          </p>
        </div>

        {error && (
          <div className="tx-error-banner">
            <span>⚠️ {error}</span>
            <button
              type="button"
              className="tx-error-close"
              aria-label="Dismiss error"
              onClick={() => setError(null)}
            >✕</button>
          </div>
        )}

        <FilterBar
          banks={availableInstitutions}
          months={availableMonths}
          categories={categories}
          bank={filterInstitution}
          month={filterMonth}
          split={filterShared}
          category={filterCategory}
          search={search}
          onBankChange={setFilterInstitution}
          onMonthChange={setFilterMonth}
          onSplitChange={setFilterShared}
          onCategoryChange={setFilterCategory}
          onSearchChange={setSearch}
          visibleCount={visible.length}
          totalCount={transactions.length}
        />

        {selected.size > 0 && (
          <BulkBar
            selectedCount={selected.size}
            sharedSelectedAmt={sharedSelectedAmt}
            onSuggest={bulkSuggest}
            onMarkUnreviewed={bulkMarkUnreviewed}
            onClear={clearSelection}
            suggesting={suggestingBulk}
          />
        )}

        <TransactionTable
          txns={visible}
          loading={loading}
          selected={selected}
          allVisibleSelected={allVisibleSelected}
          otherPersonName={personNames.person_2}
          activeExpand={activeExpand}
          onToggle={toggleSelect}
          onToggleAll={toggleAll}
          onSplitChange={handleSplitChange}
          onToggleType={handleToggleType}
          onOpenNote={openNote}
          onOpenAdj={openAdj}
          onSaveNote={saveNote}
          onSaveAdj={saveAdj}
          onCloseExpand={closeExpand}
          onToggleReviewed={handleToggleReviewed}
          editableCategory
          categories={categories}
          onCategoryChange={handleCategoryChange}
          onRemoveCategory={handleRemoveCategory}
          onDelete={handleDelete}
          onOpenDetail={openDetail}
          detailId={detailId}
          personNames={personNames}
          onSaveDetail={saveDetail}
          onCloseDetail={closeDetail}
          onDetailDraftChange={setDetailDraft}
        />

        {suggestionPreview && (
          <SuggestPreviewModal
            result={suggestionPreview}
            onApply={applySuggestions}
            onClose={() => setSuggestionPreview(null)}
          />
        )}
      </main>

      <TransactionsRail
        txns={visible}
        progress={{
          reviewed: visible.filter((t) => t.reviewed).length,
          total: visible.length,
        }}
        openTxn={detailTxn}
        draft={detailDraft}
        onOpenDetail={openDetail}
        onApplyToSimilar={applyToSimilar}
      />
    </div>
  );
}
