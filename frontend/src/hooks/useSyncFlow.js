import { useCallback, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/formatting';
import { userMessage } from '../utils/errorMessage';

// Owns the bank sync (SimpleFIN), CSV upload, and Send-to-Sheet
// flows plus the modal visibility flags they trigger. Reaches back into
// App's transaction-list hook via `reload` and surfaces failures via `setError`.
export function useSyncFlow({ reload, setError, availableMonths, filterMonth, sharedCount }) {
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sendingSheet, setSendingSheet] = useState(false);
  const [syncToast, setSyncToast] = useState(null);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [showAccountsModal, setShowAccountsModal] = useState(false);
  const [pendingCsvFile, setPendingCsvFile] = useState(null);
  const [accountsRefreshKey, setAccountsRefreshKey] = useState(0);

  // Syncs the connected SimpleFIN source.
  const syncBanks = useCallback(async (fromDate, toDate, accountIds) => {
    setShowSyncModal(false);
    setSyncing(true);
    const body = { from_date: fromDate, to_date: toDate };
    if (accountIds !== null) body.account_ids = accountIds;

    try {
      const res = await axios.post(`${API_BASE}/api/simplefin/sync`, body);
      setSyncToast(res.data);
      setAccountsRefreshKey((k) => k + 1);
      await reload();
    } catch (e) {
      setError(userMessage(e, 'Bank sync failed — please try again.'));
    } finally {
      setSyncing(false);
    }
  }, [reload, setError]);

  const handleCsvPicked = useCallback((e) => {
    const file = e.target.files[0];
    if (file) setPendingCsvFile(file);
    e.target.value = '';
  }, []);

  const submitCsvUpload = useCallback(async (formData) => {
    setUploading(true);
    try {
      const res = await axios.post(`${API_BASE}/api/upload-csv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setError(null);
      await reload();
      const file = pendingCsvFile;
      const dupes = res.data.duplicates || 0;
      const label = dupes > 0 ? `${file.name} (${dupes} already loaded, skipped)` : file.name;
      setSyncToast({
        total_new: res.data.count,
        details: [{ account: label, new: res.data.count, fetched: res.data.count + dupes }],
      });
      setPendingCsvFile(null);
    } catch (e) {
      setError(userMessage(e, 'CSV upload failed — please check the file and try again.'));
      throw e;
    } finally {
      setUploading(false);
    }
  }, [reload, setError, pendingCsvFile]);

  const sendToSheet = useCallback(async () => {
    const period = filterMonth !== 'all' ? filterMonth : null;

    if (!window.confirm(
      `Sync ${sharedCount} shared expense${sharedCount !== 1 ? 's' : ''} with the Google Sheet` +
      (period ? ` for ${period}` : '') +
      `? Your local records are kept.`
    )) return;

    setSendingSheet(true);
    try {
      const res = await axios.post(`${API_BASE}/api/sync/shared`, { period });
      const results = res.data.results || [];

      if (res.data.status === 'refused') {
        const refused = results.find((r) => r.refusal_message);
        setError(refused ? refused.refusal_message : 'Sync was refused.');
        return;
      }

      // A cycle that failed still answers 200 — without this it would render as
      // a success toast counting rows that were never written.
      if (res.data.status === 'error') {
        const failed = results.find((r) => r.error_detail);
        setError(failed
          ? `Sync failed: ${failed.error_detail}`
          : 'Sync failed — please try again.');
        return;
      }

      const pushed = results.reduce((n, r) => n + r.rows_pushed, 0);
      const pulled = results.reduce((n, r) => n + r.rows_pulled, 0);
      await reload();
      setSyncToast({
        total_new: pushed,
        details: [{ account: `Google Sheet ✓ (${pushed} sent, ${pulled} received)`, new: pushed, fetched: pushed + pulled }],
      });
    } catch (e) {
      setError(userMessage(e, 'Sync with Google Sheet failed — please try again.'));
    } finally {
      setSendingSheet(false);
    }
  }, [reload, setError, filterMonth, sharedCount]);

  return {
    syncing,
    uploading,
    sendingSheet,
    syncToast,
    setSyncToast,
    showSyncModal,
    setShowSyncModal,
    showAccountsModal,
    setShowAccountsModal,
    pendingCsvFile,
    setPendingCsvFile,
    accountsRefreshKey,
    setAccountsRefreshKey,
    syncBanks,
    handleCsvPicked,
    submitCsvUpload,
    sendToSheet,
  };
}
