import { useCallback, useMemo, useState } from 'react';
import { calculateHalf } from '../utils/formatting';

// Owns the multi-select Set for bulk operations and computes the
// "shared selected" total used by the bulk action bar.
export function useSelection(visible, transactions) {
  const [selected, setSelected] = useState(new Set());

  const toggleSelect = useCallback((id) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    }), []);

  const toggleAll = useCallback(() => {
    const visibleIds = visible.map((t) => t.id);
    setSelected((s) =>
      visibleIds.every((id) => s.has(id)) ? new Set() : new Set(visibleIds)
    );
  }, [visible]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const sharedSelectedAmt = useMemo(() => {
    let sum = 0;
    for (const t of transactions) {
      if (selected.has(t.id) && t.is_shared) {
        sum += Number(t.person_2_owes || calculateHalf(t.amount) || 0);
      }
    }
    return sum;
  }, [transactions, selected]);

  const allVisibleSelected = visible.length > 0 && visible.every((t) => selected.has(t.id));

  return {
    selected,
    toggleSelect,
    toggleAll,
    clearSelection,
    sharedSelectedAmt,
    allVisibleSelected,
  };
}
