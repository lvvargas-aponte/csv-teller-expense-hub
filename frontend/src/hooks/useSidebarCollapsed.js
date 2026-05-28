import { useCallback, useEffect, useState } from 'react';

const KEY = 'eh-sidebar-collapsed';

// Persist collapse state across both sidebars (Transactions + Finances) and
// across page reloads.
export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
  });

  useEffect(() => {
    try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch { /* quota / private mode */ }
  }, [collapsed]);

  const toggle = useCallback(() => setCollapsed((c) => !c), []);
  return [collapsed, toggle];
}
