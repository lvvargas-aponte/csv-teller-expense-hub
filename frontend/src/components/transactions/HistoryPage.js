import React, { useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../../utils/formatting';
import FilterBar from './FilterBar';
import TransactionTable from './TransactionTable';
import { useTransactions } from '../../hooks/useTransactions';
import { useFilters } from '../../hooks/useFilters';
import { useCategories } from '../../hooks/useCategories';

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
    search, setSearch,
    availableInstitutions, availableMonths, visible,
  } = useFilters(transactions);

  const {
    categories,
    addLocal: addCategoryLocal,
    remove: removeCategoryRemote,
  } = useCategories();

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

  const handleRemoveCategory = useCallback(async (name) => {
    const result = await removeCategoryRemote(name);
    // Refresh transactions so cleared categories disappear from rows.
    await reload();
    return result;
  }, [removeCategoryRemote, reload]);

  // No-op handlers for table features not used on this page.
  const noop = () => {};
  const selected = new Set();

  return (
    <main className="tx-page-wrap">
      <div className="tx-history-header">
        <h2 className="tx-history-title">Transaction History</h2>
        <p className="tx-history-sub">
          Review past transactions and adjust their categories. Type a new name to add one;
          use the ⋯ menu next to a category to remove it.
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
        bank={filterInstitution}
        month={filterMonth}
        split={filterShared}
        search={search}
        onBankChange={setFilterInstitution}
        onMonthChange={setFilterMonth}
        onSplitChange={setFilterShared}
        onSearchChange={setSearch}
        visibleCount={visible.length}
        totalCount={transactions.length}
      />

      <TransactionTable
        txns={visible}
        loading={loading}
        selected={selected}
        allVisibleSelected={false}
        otherPersonName={personNames.person_2}
        activeExpand={null}
        onToggle={noop}
        onToggleAll={noop}
        onSplitChange={noop}
        onToggleType={noop}
        onOpenNote={noop}
        onOpenAdj={noop}
        onSaveNote={noop}
        onSaveAdj={noop}
        onCloseExpand={noop}
        editableCategory
        categories={categories}
        onCategoryChange={handleCategoryChange}
        onRemoveCategory={handleRemoveCategory}
      />

    </main>
  );
}
