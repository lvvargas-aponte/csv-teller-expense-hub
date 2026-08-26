import { createContext, useContext } from 'react';

// SettingsPage saves page-wide, so leaving mid-edit drops every pane's draft
// at once. BrowserRouter has no useBlocker, so the sidebar asks this before
// navigating rather than the router blocking centrally.
export const UnsavedChangesContext = createContext({
  unsaved: false,
  setUnsaved: () => {},
});

export const useUnsavedChanges = () => useContext(UnsavedChangesContext);
