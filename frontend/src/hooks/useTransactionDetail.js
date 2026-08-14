import { useCallback, useEffect, useMemo, useState } from 'react';
import { putTransactionFields, bulkUpdateTransactions } from '../api/transactions';

// Shared open/draft/save state for the inline transaction detail row and its
// supporting rail. Used by both the Current view (App.js) and HistoryPage.
export function useTransactionDetail({
  transactions, setTransactions, setError, addCategoryLocal, listTxns,
}) {
  const [detailId, setDetailId] = useState(null);
  // Mirror of the detail form's pending {category, is_shared} so the rail's
  // "Apply to similar" card can reflect unsaved edits.
  const [detailDraft, setDetailDraft] = useState(null);

  // Looked up in the full list, not the filtered one, so the open row
  // survives filter changes.
  const detailTxn = useMemo(
    () => transactions.find((t) => t.id === detailId) || null,
    [transactions, detailId]
  );

  const openDetail = useCallback((id) => {
    setDetailDraft(null);
    setDetailId((prev) => (prev === id ? null : id));
  }, []);

  const closeDetail = useCallback(() => {
    setDetailId(null);
    setDetailDraft(null);
  }, []);

  // If the open txn leaves the rendered list (e.g. saved as reviewed on the
  // Current view, or deleted), the expanded row disappeared with it — close.
  useEffect(() => {
    if (detailId && !listTxns.some((t) => t.id === detailId)) {
      setDetailId(null);
      setDetailDraft(null);
    }
  }, [detailId, listTxns]);

  const saveDetail = useCallback(async (txn, patch) => {
    try {
      const { data } = await putTransactionFields(txn, patch);
      setTransactions((prev) => prev.map((t) => (t.id !== txn.id ? t : { ...t, ...data })));
      if (patch.category) addCategoryLocal(patch.category);
    } catch {
      setError('Could not save changes — please try again.');
    }
  }, [setTransactions, setError, addCategoryLocal]);

  // Bulk-writes the open row's pending category + split onto its merchant
  // matches. Preserves each match's reviewed flag (category/split are prep,
  // don't flip reviewed): the bulk endpoint applies one uniform `reviewed`
  // value per call, so partition into at most two calls.
  const applyToSimilar = useCallback(async (matches, { category, is_shared }) => {
    const groups = [true, false].map((flag) => ({
      reviewed: flag,
      ids: matches.filter((t) => !!t.reviewed === flag).map((t) => t.id),
    }));
    try {
      const updatedById = {};
      for (const group of groups) {
        if (!group.ids.length) continue;
        const { data } = await bulkUpdateTransactions({
          transaction_ids: group.ids,
          is_shared: !!is_shared,
          split_evenly: true,
          reviewed: group.reviewed,
          ...(category ? { category } : {}),
        });
        (data?.transactions || []).forEach((t) => { updatedById[t.id] = t; });
      }
      setTransactions((prev) => prev.map((t) => (
        updatedById[t.id] ? { ...t, ...updatedById[t.id] } : t
      )));
      if (category) addCategoryLocal(category);
    } catch {
      setError('Could not apply to similar transactions — please try again.');
    }
  }, [setTransactions, setError, addCategoryLocal]);

  return {
    detailId,
    detailTxn,
    detailDraft,
    setDetailDraft,
    openDetail,
    closeDetail,
    saveDetail,
    applyToSimilar,
  };
}
