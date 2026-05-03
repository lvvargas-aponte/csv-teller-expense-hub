import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Routes, Route, NavLink } from 'react-router-dom';

import { fmt$, txnMonthKey, calculateHalf } from './utils/formatting';
import Spin          from './components/ui/Spin';
import StatCard      from './components/ui/StatCard';
import TxnRow        from './components/transactions/TxnRow';
import EditModal     from './components/transactions/EditModal';
import NoteModal     from './components/transactions/NoteModal';
import UploadCsvModal from './components/transactions/UploadCsvModal';
import SuggestPreviewModal from './components/transactions/SuggestPreviewModal';
import { bulkSuggestCategories, applyCategoryAssignments } from './api/transactions';
import SyncModal     from './components/accounts/SyncModal';
import SyncToast     from './components/ui/SyncToast';
import AccountsModal from './components/accounts/AccountsModal';
import FinancesPage  from './components/finances/FinancesPage';
import Select        from './components/ui/Select';

const API = process.env.REACT_APP_BACKEND_URL || '';

export default function App() {
  const [transactions,  setTransactions]  = useState([]);
  const [personNames,   setPersonNames]   = useState({ person_1: 'Person 1', person_2: 'Person 2' });
  const [loading,       setLoading]       = useState(false);
  const [syncing,       setSyncing]       = useState(false);
  const [sendingSheet,  setSendingSheet]  = useState(false);
  const [uploading,     setUploading]     = useState(false);
  const [error,         setError]         = useState(null);
  const [syncToast,     setSyncToast]     = useState(null);
  const [showSyncModal,     setShowSyncModal]     = useState(false);
  const [showAccountsModal, setShowAccountsModal] = useState(false);
  const [selected,      setSelected]      = useState(new Set());
  const [filterInstitution, setFilterInstitution] = useState('all');
  const [filterShared,  setFilterShared]  = useState('all');
  const [filterMonth,   setFilterMonth]   = useState('all');
  const [editingTxn,    setEditingTxn]    = useState(null);
  const [notingTxn,     setNotingTxn]     = useState(null);
  const [pendingCsvFile, setPendingCsvFile] = useState(null);
  const [suggestionPreview, setSuggestionPreview] = useState(null);
  const [suggestingBulk,    setSuggestingBulk]    = useState(false);
  const [isDark,        setIsDark]        = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved ? saved === 'dark' : false;
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  // ── load ───────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [txRes, nameRes] = await Promise.all([
        axios.get(`${API}/api/transactions/all`),
        axios.get(`${API}/api/config/person-names`),
      ]);
      setTransactions(txRes.data);
      setPersonNames(nameRes.data);
    } catch (e) {
      setError('Could not load transactions — is the backend running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── derived state ──────────────────────────────────────────────────────────
  const availableInstitutions = React.useMemo(() => {
    const seen = new Set();
    for (const t of transactions) {
      if (t.institution) seen.add(t.institution);
    }
    return Array.from(seen).sort();
  }, [transactions]);

  const availableMonths = React.useMemo(() => {
    const seen = new Map();
    for (const t of transactions) {
      const m = txnMonthKey(t.date);
      if (m && !seen.has(m.key)) seen.set(m.key, m.label);
    }
    return Array.from(seen.entries())
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([key, label]) => ({ key, label }));
  }, [transactions]);

  const visible = React.useMemo(() => transactions.filter((t) => {
    if (filterInstitution !== 'all' && (t.institution || '') !== filterInstitution) return false;
    if (filterShared === 'shared'   && !t.is_shared) return false;
    if (filterShared === 'personal' &&  t.is_shared) return false;
    if (filterMonth  !== 'all') {
      const m = txnMonthKey(t.date);
      if (!m || m.key !== filterMonth) return false;
    }
    return true;
  }), [transactions, filterInstitution, filterShared, filterMonth]);

  const sharedCount = visible.filter((t) => t.is_shared).length;
  const sharedTotal = visible
    .filter((t) => t.is_shared)
    .reduce((s, t) => s + Math.abs(parseFloat(t.amount) || 0), 0);

  const selectedVisibleCount = visible.filter((t) => selected.has(t.id)).length;
  const allVisibleSelected   = visible.length > 0 && visible.every((t) => selected.has(t.id));

  // ── selection ──────────────────────────────────────────────────────────────
  const toggleSelect = useCallback((id) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    }), []);

  const toggleAll = useCallback(() => {
    const visibleIds = visible.map((t) => t.id);
    setSelected((s) =>
      visibleIds.every((id) => s.has(id)) ? new Set() : new Set(visibleIds)
    );
  }, [visible]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  // ── actions ────────────────────────────────────────────────────────────────
  const quickMark = useCallback(async (txn, isShared) => {
    const half = calculateHalf(txn.amount);
    await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
      is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
      who: txn.who || '', what: txn.what || '', notes: txn.notes || '',
    });
    // The backend flips `reviewed: true` on any user edit — mirror that
    // locally so the Unreviewed tile reacts immediately without a reload.
    setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
      ...t, is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
      reviewed: true,
    }));
  }, []);

  // Manual override for a misclassified CR/DR badge — clicking the badge in
  // TxnRow flips the type. Preserves all other fields including `reviewed`:
  // a CR/DR fix is a categorization correction, not a split decision, so it
  // should NOT light up the Personal/50-50 toggle as if the user had reviewed
  // the row.
  const toggleType = useCallback(async (txn, nextType) => {
    await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
      is_shared: !!txn.is_shared,
      who:           txn.who   || '',
      what:          txn.what  || '',
      notes:         txn.notes || '',
      person_1_owes: txn.person_1_owes || 0,
      person_2_owes: txn.person_2_owes || 0,
      reviewed:      !!txn.reviewed,
      transaction_type: nextType,
    });
    setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
      ...t, transaction_type: nextType,
    }));
  }, []);

  const bulkMark = useCallback(async (isShared) => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    try {
      await axios.put(`${API}/api/transactions/bulk`, {
        transaction_ids: ids,
        is_shared: isShared,
        split_evenly: true,
      });
      await load();
      clearSelection();
    } catch (e) {
      setError('Bulk update failed — please try again');
    }
  }, [visible, selected, load, clearSelection]);

  const bulkSuggest = useCallback(async () => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    setSuggestingBulk(true);
    try {
      const r = await bulkSuggestCategories(ids);
      setSuggestionPreview(r.data);
    } catch (e) {
      setError('Could not get category suggestions — please try again');
    } finally {
      setSuggestingBulk(false);
    }
  }, [visible, selected]);

  const applySuggestions = useCallback(async (items) => {
    try {
      await applyCategoryAssignments(items);
      setSuggestionPreview(null);
      clearSelection();
      await load();
    } catch (e) {
      setError('Could not apply categories — please try again');
    }
  }, [load, clearSelection]);

  const saveEdit = useCallback(async (form) => {
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(editingTxn.id)}`, form);
      setEditingTxn(null);
      await load();
    } catch (e) {
      setError('Could not save changes — please try again');
    }
  }, [editingTxn, load]);

  const saveNote = useCallback(async (notes) => {
    const txn = notingTxn;
    try {
      await axios.put(`${API}/api/transactions/${encodeURIComponent(txn.id)}`, {
        is_shared: txn.is_shared,
        who: txn.who || '',
        what: txn.what || '',
        person_1_owes: txn.person_1_owes || 0,
        person_2_owes: txn.person_2_owes || 0,
        notes,
      });
      setNotingTxn(null);
      await load();
    } catch (e) {
      setError('Could not save note — please try again');
    }
  }, [notingTxn, load]);

  const syncTeller = useCallback(async (fromDate, toDate, accountIds) => {
    setShowSyncModal(false);
    setSyncing(true);
    try {
      const body = { from_date: fromDate, to_date: toDate };
      if (accountIds !== null) body.account_ids = accountIds;
      const res = await axios.post(`${API}/api/teller/sync`, body);
      setSyncToast(res.data);
      await load();
    } catch (e) {
      setError('Teller sync failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSyncing(false);
    }
  }, [load]);

  const handleCsvPicked = useCallback((e) => {
    const file = e.target.files[0];
    if (file) setPendingCsvFile(file);
    e.target.value = '';
  }, []);

  const submitCsvUpload = useCallback(async (formData) => {
    setUploading(true);
    try {
      const res = await axios.post(`${API}/api/upload-csv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setError(null);
      await load();
      const file = pendingCsvFile;
      const dupes = res.data.duplicates || 0;
      const label = dupes > 0 ? `${file.name} (${dupes} already loaded, skipped)` : file.name;
      setSyncToast({
        total_new: res.data.count,
        details: [{ account: label, new: res.data.count, fetched: res.data.count + dupes }],
      });
      setPendingCsvFile(null);
    } catch (e) {
      setError('CSV upload failed: ' + (e.response?.data?.detail || e.message));
      throw e;
    } finally {
      setUploading(false);
    }
  }, [load, pendingCsvFile]);

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
      const res = await axios.post(`${API}/api/send-to-gsheet`, {
        sheet_name:   sheetLabel,
        filter_month: filterMonth !== 'all' ? filterMonth : null,
      });
      await load();
      setSyncToast({
        total_new: res.data.count,
        details: [{ account: `Google Sheet ✓ (${res.data.sheet_name})`, new: res.data.count, fetched: res.data.count }],
      });
    } catch (e) {
      setError('Send failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSendingSheet(false);
    }
  }, [availableMonths, filterMonth, sharedCount, load]);

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="app-root">

      {/* header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="brand">
            <span className="brand-icon">💳</span>
            <span>Expense Tracker</span>
          </div>
          <div className="header-actions">
            <button type="button"
                    className="btn btn-secondary"
                    style={{ padding: '8px 12px', fontSize: 16 }}
                    onClick={() => setIsDark((d) => !d)}
                    aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                    title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? '☀️' : '🌙'}
            </button>

            <button type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowAccountsModal(true)}
                    title="Manage linked bank accounts"
            >
              🏦 Accounts
            </button>

            <button type="button"
                    className="btn btn-teller"
                    onClick={() => setShowSyncModal(true)}
                    disabled={syncing}
            >
              {syncing ? <><Spin /> Syncing…</> : '⟳ Sync Banks'}
            </button>
          </div>

          <nav className="app-nav">
            <NavLink to="/" end className={({ isActive }) => 'nav-tab' + (isActive ? ' nav-tab--active' : '')}>
              Transactions
            </NavLink>
            <NavLink to="/finances" className={({ isActive }) => 'nav-tab' + (isActive ? ' nav-tab--active' : '')}>
              Finances
            </NavLink>
          </nav>

        </div>
      </header>

      <Routes>
        <Route path="/finances" element={<FinancesPage />} />
        <Route path="/" element={
          <main className="app-main">
            {error && (
              <div className="error-banner">
                ⚠️ {error}
                <button type="button" className="error-close" aria-label="Dismiss error" onClick={() => setError(null)}>✕</button>
              </div>
            )}

            {/* stats */}
            <div className="stats-bar">
              <StatCard label="Total"      value={transactions.length} />
              <StatCard label="Shared"     value={sharedCount}          accent="#10b981" />
              <StatCard label="Shared $"   value={fmt$(sharedTotal)}    accent="#10b981" />
              <StatCard label="Unreviewed" value={transactions.filter((t) => !t.reviewed).length} accent="#f59e0b" />
            </div>

            {/* import / export */}
            <div className="txn-actions">
              <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                {uploading ? <><Spin /> Uploading…</> : '📂 Upload CSV'}
                <input type="file" accept=".csv" hidden onChange={handleCsvPicked} disabled={uploading} />
              </label>
              <button type="button"
                      className="btn btn-green btn-sm"
                      onClick={sendToSheet}
                      disabled={sharedCount === 0 || sendingSheet}
              >
                {sendingSheet ? <Spin /> : '📊'} Send to Sheet{sharedCount > 0 ? ` (${sharedCount})` : ''}
              </button>
            </div>

            {/* toolbar */}
            <div className="toolbar">
              <div className="filters">
                <Select
                  aria-label="Filter by bank"
                  value={filterInstitution}
                  onChange={setFilterInstitution}
                  options={[
                    { value: 'all', label: 'All banks' },
                    ...availableInstitutions.map((inst) => ({ value: inst, label: inst })),
                  ]}
                />
                <Select
                  aria-label="Filter by type"
                  value={filterShared}
                  onChange={setFilterShared}
                  options={[
                    { value: 'all',      label: 'All types' },
                    { value: 'shared',   label: 'Shared only' },
                    { value: 'personal', label: 'Personal only' },
                  ]}
                />
                <Select
                  aria-label="Filter by month"
                  value={filterMonth}
                  onChange={setFilterMonth}
                  options={[
                    { value: 'all', label: 'All months' },
                    ...availableMonths.map(({ key, label }) => ({ value: key, label })),
                  ]}
                />
              </div>

              {selectedVisibleCount > 0 && (
                <div className="bulk-bar">
                  <span className="bulk-count">{selectedVisibleCount} selected</span>
                  <button type="button" className="btn btn-green btn-sm" onClick={() => bulkMark(true)}>
                    ✓ Mark shared (50/50)
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => bulkMark(false)}>
                    Mark personal
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm"
                          onClick={bulkSuggest} disabled={suggestingBulk}
                          title="Ask the local AI to suggest categories for selected uncategorized transactions">
                    {suggestingBulk ? <><Spin /> Thinking…</> : '✨ Suggest categories'}
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={clearSelection}>
                    Clear
                  </button>
                </div>
              )}
            </div>

            {/* table */}
            <div className="table-wrap">
              {loading ? (
                <div className="empty-state"><Spin large /><br />Loading…</div>
              ) : visible.length === 0 ? (
                <div className="empty-state">
                  No transactions yet.<br />
                  <span className="empty-state-hint">
                    Click <strong>Sync Banks</strong> to pull from Teller, or <strong>Upload CSV</strong> to import a file.
                  </span>
                </div>
              ) : (
                <table className="txn-table">
                  <thead>
                    <tr>
                      <th className="col-checkbox">
                        <input
                          type="checkbox"
                          aria-label="Select all visible transactions"
                          checked={allVisibleSelected}
                          onChange={toggleAll}
                          style={{ cursor: 'pointer' }}
                        />
                      </th>
                      <th>Date</th>
                      <th>Description</th>
                      <th className="col-amount">Amount</th>
                      <th>Source</th>
                      <th>Split</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((txn) => (
                      <TxnRow
                        key={txn.id}
                        txn={txn}
                        otherPersonName={personNames.person_2}
                        isSelected={selected.has(txn.id)}
                        onToggle={toggleSelect}
                        onQuickMark={quickMark}
                        onToggleType={toggleType}
                        onEdit={() => setEditingTxn(txn)}
                        onNote={() => setNotingTxn(txn)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </main>
        } />
      </Routes>

      {showSyncModal     && <SyncModal onSync={syncTeller} onClose={() => setShowSyncModal(false)} />}
      {showAccountsModal && <AccountsModal onClose={() => setShowAccountsModal(false)} />}
      {pendingCsvFile && (
        <UploadCsvModal
          file={pendingCsvFile}
          onSubmit={submitCsvUpload}
          onClose={() => setPendingCsvFile(null)}
        />
      )}
      {editingTxn    && <EditModal txn={editingTxn} personNames={personNames} onSave={saveEdit} onClose={() => setEditingTxn(null)} />}
      {notingTxn     && <NoteModal txn={notingTxn} onSave={saveNote} onClose={() => setNotingTxn(null)} />}
      {suggestionPreview && (
        <SuggestPreviewModal
          result={suggestionPreview}
          onApply={applySuggestions}
          onClose={() => setSuggestionPreview(null)}
        />
      )}
      {syncToast     && <SyncToast result={syncToast} onClose={() => setSyncToast(null)} />}
    </div>
  );
}
