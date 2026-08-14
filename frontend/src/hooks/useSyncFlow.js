import { useCallback, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/formatting';
import { userMessage } from '../utils/errorMessage';

// Owns the bank sync (Teller + SimpleFIN), CSV upload, and Send-to-Sheet
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

  // Syncs every connected source (Teller + SimpleFIN) in parallel. Either one
  // is allowed to have zero connections configured — that source's request
  // just 500s and is filtered out below — so this works whether the
  // household uses Teller, SimpleFIN, or both side by side.
  const syncBanks = useCallback(async (fromDate, toDate, accountIds) => {
    setShowSyncModal(false);
    setSyncing(true);
    const body = { from_date: fromDate, to_date: toDate };
    if (accountIds !== null) body.account_ids = accountIds;

    const [tellerResult, simplefinResult] = await Promise.allSettled([
      axios.post(`${API_BASE}/api/teller/sync`, body),
      axios.post(`${API_BASE}/api/simplefin/sync`, body),
    ]);

    const successes = [tellerResult, simplefinResult]
      .filter((r) => r.status === 'fulfilled')
      .map((r) => r.value.data);

    if (successes.length === 0) {
      const firstError = tellerResult.reason || simplefinResult.reason;
      setError(userMessage(firstError, 'Bank sync failed — please try again.'));
      setSyncing(false);
      return;
    }

    const merged = successes.reduce((acc, r) => ({
      total_new: (acc.total_new || 0) + (r.total_new || 0),
      details: [...(acc.details || []), ...(r.details || [])],
    }), {});
    setSyncToast(merged);
    setAccountsRefreshKey((k) => k + 1);
    await reload();
    setSyncing(false);
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
    const activeMonth = availableMonths.find((m) => m.key === filterMonth);
    const sheetLabel  = activeMonth ? activeMonth.label : null;

    if (!window.confirm(
      `Send ${sharedCount} shared expense${sharedCount !== 1 ? 's' : ''} to Google Sheet` +
      (sheetLabel ? ` "${sheetLabel}"` : '') +
      `? They'll be cleared from the queue.`
    )) return;

    setSendingSheet(true);
    try {
      const res = await axios.post(`${API_BASE}/api/send-to-gsheet`, {
        sheet_name:   sheetLabel,
        filter_month: filterMonth !== 'all' ? filterMonth : null,
      });
      await reload();
      setSyncToast({
        total_new: res.data.count,
        details: [{ account: `Google Sheet ✓ (${res.data.sheet_name})`, new: res.data.count, fetched: res.data.count }],
      });
    } catch (e) {
      setError(userMessage(e, 'Send to Google Sheet failed — please try again.'));
    } finally {
      setSendingSheet(false);
    }
  }, [reload, setError, availableMonths, filterMonth, sharedCount]);

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
