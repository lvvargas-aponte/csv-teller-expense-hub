import { createContext, useContext } from 'react';

// Sync outlives the page that started it: an upload or bank pull begun on
// Transactions keeps its modal and its result visible after the user
// navigates away, instead of finishing unseen.
export const SyncContext = createContext(null);

export const useSync = () => useContext(SyncContext);
