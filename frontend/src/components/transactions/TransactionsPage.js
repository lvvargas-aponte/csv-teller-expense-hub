import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';

import { calculateHalf, API_BASE } from '../../utils/formatting';
import SyncPanel        from './SyncPanel';
import ControlBar       from './ControlBar';
import BulkBar          from './BulkBar';
import FilterBar        from './FilterBar';
import TransactionTable from './TransactionTable';
import SuggestPreviewModal from './SuggestPreviewModal';
import TransactionsRail from './TransactionsRail';
import { bulkSuggestCategories, applyCategoryAssignments, deleteTransaction, previewDuplicates, applyDeduplication } from '../../api/transactions';
import HistoryPage      from './HistoryPage';
import SharedPage       from '../shared/SharedPage';
import { useTransactions } from '../../hooks/useTransactions';
import { useFilters } from '../../hooks/useFilters';
import { useSelection } from '../../hooks/useSelection';
import { useSync } from '../../contexts/SyncContext';
import { useCategories } from '../../hooks/useCategories';
import { useTransactionDetail } from '../../hooks/useTransactionDetail';
import { getBalancesSummary } from '../../api/balances';

const API = API_BASE;

// view: 'current' | 'shared' | 'history'
export default function TransactionsPage({ view }) {
  const {
    transactions, personNames, loading, error, setError, setTransactions, reload,
  } = useTransactions();

  const {
    filterInstitution, setFilterInstitution,
    filterShared, setFilterShared,
    filterMonth, setFilterMonth,
    filterCategory, setFilterCategory,
    search, setSearch,
    availableInstitutions, availableMonths, visible, stats,
  } = useFilters(transactions);

  // Current view filters out reviewed txns; selection must follow that list
  // so the header Select-All only toggles the rows actually rendered.
  const unreviewedVisibleEarly = useMemo(
    () => visible.filter((t) => !t.reviewed),
    [visible],
  );

  const {
    selected, toggleSelect, toggleAll, clearSelection,
    sharedSelectedAmt, allVisibleSelected,
  } = useSelection(unreviewedVisibleEarly, transactions);

  const {
    categories, addLocal: addCategoryLocal, remove: removeCategoryRemote,
  } = useCategories();

  // Sync lives at shell level (App.js) so an in-flight bank pull or CSV
  // upload survives navigating away from Transactions. This page only
  // registers what the shell can't know on its own: how to refresh this
  // page's list, where to surface an error, and the filter/count
  // `sendToSheet` needs.
  const sync = useSync();
  useEffect(() => {
    sync.registerSyncPage({ reload, setError, filterMonth, sharedCount: stats.shared });
    return () => sync.registerSyncPage({ reload: null, setError: null, filterMonth: 'all', sharedCount: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sync.registerSyncPage, reload, setError, filterMonth, stats.shared]);

  const [activeExpand, setActiveExpand] = useState(null);  // 'note-{id}' | 'adj-{id}' | null
  const [suggestionPreview, setSuggestionPreview] = useState(null);
  const [suggestingBulk, setSuggestingBulk] = useState(false);
  const [dedupingNow, setDedupingNow] = useState(false);

  const {
    detailId, detailTxn, detailDraft, setDetailDraft,
    openDetail, closeDetail, saveDetail, applyToSimilar,
  } = useTransactionDetail({
    transactions, setTransactions, setError, addCategoryLocal,
    listTxns: unreviewedVisibleEarly,
  });

  // ── single-row split toggle (P / ½) ────────────────────────────────────────
  // Personal = decision is done → auto-reviewed.
  // Shared   = still pending Google Sheet send → DO NOT auto-review; sending
  //           to Sheets removes the row from the queue entirely (sheets.py).
  const handleSplitChange = useCallback(async (txn, isShared) => {
    const half = calculateHalf(txn.amount);
    const nextReviewed = isShared ? !!txn.reviewed : true;
    await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
      is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
      who: txn.who || '', what: txn.what || '', notes: txn.notes || '',
      reviewed: nextReviewed,
    });
    setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
      ...t,
      is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
      reviewed: nextReviewed,
    }));
  }, [setTransactions]);

  // CR/DR badge flip — doesn't mark as reviewed (it's a categorization fix).
  const handleToggleType = useCallback(async (txn, nextType) => {
    await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
      is_shared: !!txn.is_shared,
      who:           txn.who   || '',
      what:          txn.what  || '',
      notes:         txn.notes || '',
      person_1_owes: txn.person_1_owes || 0,
      person_2_owes: txn.person_2_owes || 0,
      reviewed:      !!txn.reviewed,
      transaction_type: nextType,
    });
    setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
      ...t, transaction_type: nextType,
    }));
  }, [setTransactions]);

  // ── inline expands: note + split-adjust + transfer ─────────────────────────
  const openNote     = useCallback((id) => setActiveExpand(id ? `note-${id}`     : null), []);
  const openAdj      = useCallback((id) => setActiveExpand(id ? `adj-${id}`      : null), []);
  const openTransfer = useCallback((id) => setActiveExpand(id ? `transfer-${id}` : null), []);
  const closeExpand  = useCallback(() => setActiveExpand(null), []);

  // Manual-account map for the transfer chip — refreshed alongside transactions
  // and when the user saves a transfer (the destination balance may have shifted).
  const [manualAccountsById, setManualAccountsById] = useState({});
  const reloadManualAccounts = useCallback(async () => {
    try {
      const r = await getBalancesSummary(false);
      const map = {};
      (r.data?.accounts || []).forEach((a) => { if (a.manual) map[a.id] = a; });
      setManualAccountsById(map);
    } catch { /* non-fatal — chip just shows generic label */ }
  }, []);
  useEffect(() => { reloadManualAccounts(); }, [reloadManualAccounts]);

  const saveNote = useCallback(async (txn, notes) => {
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared: !!txn.is_shared,
        who: txn.who || '', what: txn.what || '',
        person_1_owes: txn.person_1_owes || 0,
        person_2_owes: txn.person_2_owes || 0,
        notes,
        reviewed: !!txn.reviewed,  // notes are prep, don't flip reviewed
      });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : { ...t, notes }));
      setActiveExpand(null);
    } catch {
      setError('Could not save note — please try again');
    }
  }, [setTransactions, setError]);

  const handleCategoryChange = useCallback(async (txn, nextCategory) => {
    const trimmed = (nextCategory || '').trim();
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
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

  const handleRemoveCategory = useCallback(async (name) => {
    const result = await removeCategoryRemote(name);
    await reload();
    return result;
  }, [removeCategoryRemote, reload]);

  const saveTransfer = useCallback(async (txn, accountId) => {
    const next = accountId || null;
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared:     !!txn.is_shared,
        who:           txn.who   || '',
        what:          txn.what  || '',
        notes:         txn.notes || '',
        person_1_owes: txn.person_1_owes || 0,
        person_2_owes: txn.person_2_owes || 0,
        reviewed:      true,
        transfer_to_account_id: accountId || '',
      });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
        ...t, transfer_to_account_id: next, reviewed: true,
      }));
      setActiveExpand(null);
      reloadManualAccounts();
    } catch {
      setError('Could not save transfer — please try again');
    }
  }, [setTransactions, setError, reloadManualAccounts]);

  const saveAdj = useCallback(async (txn, { person_1_owes, person_2_owes }) => {
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared: true,
        who: txn.who || '', what: txn.what || '', notes: txn.notes || '',
        person_1_owes,
        person_2_owes,
        reviewed: !!txn.reviewed,  // still shared/pending sheet send — don't flip
      });
      setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
        ...t, is_shared: true, person_1_owes, person_2_owes,
      }));
      setActiveExpand(null);
    } catch {
      setError('Could not save split — please try again');
    }
  }, [setTransactions, setError]);

  // ── bulk actions ───────────────────────────────────────────────────────────
  // Personal bulk = decided → reviewed. Shared bulk = pending sheet send →
  // explicitly unreviewed (the backend defaults `reviewed` to True when
  // omitted, so we must pass `false` to override).
  const bulkMark = useCallback(async (isShared) => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    try {
      await axios.put(`${API}/api/transactions/bulk`, {
        transaction_ids: ids,
        is_shared: isShared,
        split_evenly: true,
        reviewed: !isShared,
      });
      await reload();
      clearSelection();
    } catch {
      setError('Bulk update failed — please try again');
    }
  }, [visible, selected, reload, clearSelection, setError]);

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

  // ── reviewed toggles (inline + bulk) ───────────────────────────────────────
  const handleToggleReviewed = useCallback(async (txn, nextReviewed) => {
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared:     !!txn.is_shared,
        who:           txn.who   || '',
        what:          txn.what  || '',
        notes:         txn.notes || '',
        person_1_owes: txn.person_1_owes || 0,
        person_2_owes: txn.person_2_owes || 0,
        reviewed:      !!nextReviewed,
      });
      setTransactions((prev) => prev.map((t) =>
        t.id !== txn.id ? t : { ...t, reviewed: !!nextReviewed }
      ));
    } catch {
      setError('Could not update reviewed state — please try again.');
    }
  }, [setTransactions, setError]);

  const handleDeleteTransaction = useCallback(async (txn) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete this transaction?\n\n${txn.date} · ${txn.description}`)) return;
    try {
      await deleteTransaction(txn.id);
      setTransactions((prev) => prev.filter((t) => t.id !== txn.id));
    } catch {
      setError('Could not delete transaction — please try again.');
    }
  }, [setTransactions, setError]);

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

  const bulkMarkReviewed = useCallback(async () => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    try {
      await axios.put(`${API}/api/transactions/bulk/reviewed`, {
        transaction_ids: ids,
        reviewed: true,
      });
      setTransactions((prev) => prev.map((t) =>
        ids.includes(t.id) ? { ...t, reviewed: true } : t
      ));
      clearSelection();
    } catch {
      setError('Could not mark as reviewed — please try again.');
    }
  }, [visible, selected, setTransactions, clearSelection, setError]);

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

  // Alias for readability at the render site.
  const unreviewedVisible = unreviewedVisibleEarly;

  return (
    <>
      <div className="eh-main" id="eh-main">
        {view === 'current' ? (
          <div className="tx-layout">
            <main className="tx-page-wrap">
              <SyncPanel
                onOpenAccounts={() => sync.setShowAccountsModal(true)}
                onOpenSync={() => sync.setShowSyncModal(true)}
                syncing={sync.syncing}
                refreshKey={sync.accountsRefreshKey}
              />

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

              <ControlBar
                totalCount={stats.total}
                sharedCount={stats.shared}
                sharedAmt={stats.sharedAmt}
                unreviewedCount={stats.unreviewed}
                uploading={sync.uploading}
                dedupingNow={dedupingNow}
                onPickCsv={sync.handleCsvPicked}
                onFindDuplicates={handleFindDuplicates}
              />

              {selected.size > 0 && (
                <BulkBar
                  selectedCount={selected.size}
                  sharedSelectedAmt={sharedSelectedAmt}
                  onMarkPersonal={() => bulkMark(false)}
                  onMark5050={() => bulkMark(true)}
                  onMarkReviewed={bulkMarkReviewed}
                  onSuggest={bulkSuggest}
                  onClear={clearSelection}
                  suggesting={suggestingBulk}
                />
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

              {!loading && transactions.length > 0 && unreviewedVisible.length === 0 ? (
                <div className="tx-empty-state">
                  <div className="tx-empty-state-icon" aria-hidden="true">🎉</div>
                  <div className="tx-empty-state-title">All caught up!</div>
                  <div className="tx-empty-state-sub">
                    Every transaction here has been reviewed.
                    Add more via sync or CSV upload, or switch to History
                    to revisit past transactions.
                  </div>
                </div>
              ) : (
                <TransactionTable
                  txns={unreviewedVisible}
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
                  onOpenTransfer={openTransfer}
                  onSaveNote={saveNote}
                  onSaveAdj={saveAdj}
                  onSaveTransfer={saveTransfer}
                  onCloseExpand={closeExpand}
                  onToggleReviewed={handleToggleReviewed}
                  onDelete={handleDeleteTransaction}
                  manualAccountsById={manualAccountsById}
                  editableCategory
                  categories={categories}
                  onCategoryChange={handleCategoryChange}
                  onRemoveCategory={handleRemoveCategory}
                  onOpenDetail={openDetail}
                  detailId={detailId}
                  personNames={personNames}
                  onSaveDetail={saveDetail}
                  onCloseDetail={closeDetail}
                  onDetailDraftChange={setDetailDraft}
                />
              )}
            </main>

            <TransactionsRail
              txns={visible}
              progress={{
                reviewed: visible.length - unreviewedVisible.length,
                total: visible.length,
              }}
              openTxn={detailTxn}
              draft={detailDraft}
              personName={personNames.person_2}
              onOpenDetail={openDetail}
              onApplyToSimilar={applyToSimilar}
              onSendToSheet={sync.sendToSheet}
              sendingSheet={sync.sendingSheet}
            />
          </div>
        ) : view === 'shared' ? (
          <SharedPage />
        ) : (
          <HistoryPage />
        )}
      </div>

      {suggestionPreview && (
        <SuggestPreviewModal
          result={suggestionPreview}
          onApply={applySuggestions}
          onClose={() => setSuggestionPreview(null)}
        />
      )}
    </>
  );
}
