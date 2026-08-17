import { useCallback, useEffect, useRef, useState } from 'react';

import { getLayout, resetLayout, saveLayout } from '../../../api/layout';

// The default arrangement, and the source of truth for which cards exist.
// Ordered as the narrative arc the dashboard was designed around: Position →
// Flow → Trend → Assets → Constraints → Commitments → Signals. A user who
// rearranges is overriding an argument, not filling in a blank.
export const DEFAULT_LAYOUT = [
  { i: 'net_worth',        x: 0, y: 0,  w: 12, h: 8, minW: 4, minH: 5 },
  { i: 'cash_flow',        x: 0, y: 8,  w: 6,  h: 7, minW: 3, minH: 4 },
  { i: 'spending',         x: 6, y: 8,  w: 6,  h: 7, minW: 3, minH: 4 },
  { i: 'income_expenses',  x: 0, y: 15, w: 12, h: 7, minW: 4, minH: 4 },
  { i: 'balances',         x: 0, y: 22, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'portfolio',        x: 6, y: 22, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'credit',           x: 0, y: 28, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'budgets',          x: 6, y: 28, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'goals',            x: 0, y: 34, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'recurring',        x: 6, y: 34, w: 6,  h: 6, minW: 3, minH: 3 },
  { i: 'alerts',           x: 0, y: 40, w: 12, h: 6, minW: 4, minH: 3 },
];

const KNOWN_IDS = new Set(DEFAULT_LAYOUT.map((item) => item.i));

/**
 * Reconcile a saved layout against the cards that exist today.
 *
 * A layout saved before a card shipped has no entry for it, and one saved
 * before a card was removed has a stale entry. Dropping unknown ids and
 * appending missing ones at the bottom means shipping a new card never
 * strands a user on an arrangement that silently omits it.
 */
export function reconcile(saved) {
  if (!Array.isArray(saved) || saved.length === 0) return DEFAULT_LAYOUT;

  const kept = saved.filter((item) => KNOWN_IDS.has(item.i));
  const present = new Set(kept.map((item) => item.i));
  const maxY = kept.reduce((max, item) => Math.max(max, item.y + item.h), 0);

  const appended = DEFAULT_LAYOUT
    .filter((item) => !present.has(item.i))
    .map((item, index) => ({ ...item, x: 0, y: maxY + index * item.h }));

  return [...kept, ...appended];
}

export default function useDashboardLayout() {
  const [layout, setLayout] = useState(DEFAULT_LAYOUT);
  const [hidden, setHidden] = useState([]);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  // Skip the first onLayoutChange, which react-grid-layout fires on mount
  // with the layout we just handed it — persisting that would write the
  // default over a saved arrangement.
  const loaded = useRef(false);

  useEffect(() => {
    getLayout()
      .then((r) => {
        setLayout(reconcile(r.data?.layout));
        setHidden(r.data?.hidden || []);
      })
      .catch(() => { /* defaults are a fine fallback */ })
      .finally(() => { loaded.current = true; });
  }, []);

  const handleLayoutChange = useCallback((next) => {
    if (!loaded.current) return;
    setLayout(next.map(({ i, x, y, w, h, minW, minH }) => ({ i, x, y, w, h, minW, minH })));
    setDirty(true);
  }, []);

  const hide = useCallback((id) => {
    setHidden((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setDirty(true);
  }, []);

  const show = useCallback((id) => {
    setHidden((prev) => prev.filter((h) => h !== id));
    setDirty(true);
  }, []);

  const persist = useCallback(() => {
    setDirty(false);
    return saveLayout({ layout, hidden }).catch(() => setDirty(true));
  }, [layout, hidden]);

  const restoreDefaults = useCallback(() => {
    setLayout(DEFAULT_LAYOUT);
    setHidden([]);
    setDirty(false);
    return resetLayout().catch(() => {});
  }, []);

  return {
    layout, hidden, editing, dirty,
    setEditing, handleLayoutChange, hide, show, persist, restoreDefaults,
  };
}
