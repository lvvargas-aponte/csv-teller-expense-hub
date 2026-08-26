import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { useSyncFlow } from '../hooks/useSyncFlow';

// Sync outlives the page that started it: an upload or bank pull begun on
// Transactions keeps its modal and its result visible after the user
// navigates away, instead of finishing unseen.
export const SyncContext = createContext(null);

export const useSync = () => useContext(SyncContext);

// Owns the shell-level wiring for sync: a single `useSyncFlow` call plus the
// registration channel a page uses to plug in what the shell can't know on
// its own — how to refresh its own list, where to surface an error, and the
// filterMonth/sharedCount values `sendToSheet` closes over directly (it's
// called with no args, so those have to be live at the one `useSyncFlow`
// call site — a ref would go stale silently since nothing re-renders to
// refresh it). Lives beside the context because it has no dependency on
// App's JSX or routing.
export function useSyncProvider() {
  const reloadRef = useRef(() => {});
  const setErrorRef = useRef(() => {});
  const [syncPageMeta, setSyncPageMeta] = useState({ filterMonth: 'all', sharedCount: 0 });
  const reload = useCallback((...args) => reloadRef.current(...args), []);
  const setError = useCallback((...args) => setErrorRef.current(...args), []);

  const syncFlow = useSyncFlow({
    reload, setError, filterMonth: syncPageMeta.filterMonth, sharedCount: syncPageMeta.sharedCount,
  });

  const registerSyncPage = useCallback(({ reload: pageReload, setError: pageSetError, filterMonth, sharedCount }) => {
    reloadRef.current = pageReload || (() => {});
    setErrorRef.current = pageSetError || (() => {});
    setSyncPageMeta((prev) => (prev.filterMonth === filterMonth && prev.sharedCount === sharedCount)
      ? prev
      : { filterMonth: filterMonth ?? 'all', sharedCount: sharedCount ?? 0 });
  }, []);

  const syncValue = useMemo(
    () => ({ ...syncFlow, registerSyncPage }),
    [syncFlow, registerSyncPage],
  );

  return { syncFlow, syncValue };
}
