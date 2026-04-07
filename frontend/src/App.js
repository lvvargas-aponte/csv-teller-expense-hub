import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import 'bootstrap/dist/css/bootstrap.min.css';

const API = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

// ─── helpers ──────────────────────────────────────────────────────────────────
const fmt$ = (n) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
        Math.abs(parseFloat(n) || 0)
    );

const fmtDate = (s) => {
  const d = new Date(s + 'T00:00:00');
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const toYMD = (d) => d.toISOString().split('T')[0];

function prevMonthRange() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0);
  return { from: toYMD(first), to: toYMD(last) };
}

function thisMonthRange() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  return { from: toYMD(first), to: toYMD(now) };
}

const SOURCE_COLOR = { discover: '#f59e0b', barclays: '#3b82f6', teller: '#10b981', unknown: '#6b7280' };

// ─── Backdrop — only closes on click of the dark area itself ─────────────────
function Backdrop({ onClose, children, zIndex = 200 }) {
  const ref = useRef(null);
  return (
      <div
          ref={ref}
          onMouseDown={(e) => { if (e.target === ref.current) onClose(); }}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.72)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex, padding: 20, boxSizing: 'border-box',
          }}
      >
        {children}
      </div>
  );
}

// ─── Edit modal ───────────────────────────────────────────────────────────────
function EditModal({ txn, personNames, onSave, onClose }) {
  const [form, setForm] = useState({
    is_shared:     txn.is_shared     || false,
    who:           txn.who           || '',
    what:          txn.what          || '',
    person_1_owes: txn.person_1_owes || 0,
    person_2_owes: txn.person_2_owes || 0,
    notes:         txn.notes         || '',
  });

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const split50 = (e) => {
    e.preventDefault();
    const half = parseFloat((Math.abs(parseFloat(txn.amount)) / 2).toFixed(2));
    setForm((f) => ({ ...f, person_1_owes: half, person_2_owes: half }));
  };

  return (
      <Backdrop onClose={onClose}>
        <div style={styles.modal}>
          <div style={styles.modalHeader}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={styles.modalTitle}>{txn.description}</div>
              <div style={styles.modalSub}>{fmtDate(txn.date)} · {fmt$(txn.amount)}</div>
            </div>
            <button type="button" style={styles.closeBtn} onClick={onClose}>✕</button>
          </div>

          <div style={styles.modalBody}>
            <div style={styles.toggleRow}>
              <span style={styles.label}>Type</span>
              <div style={styles.segmented}>
                {['Personal', 'Shared'].map((opt) => (
                    <button
                        key={opt} type="button"
                        onClick={() => set('is_shared', opt === 'Shared')}
                        style={{ ...styles.seg, ...(form.is_shared === (opt === 'Shared') ? styles.segActive : {}) }}
                    >
                      {opt}
                    </button>
                ))}
              </div>
            </div>

            {form.is_shared && (
                <>
                  <div style={styles.row2}>
                    <div style={styles.fieldGroup}>
                      <label style={styles.label}>Who paid?</label>
                      <input style={styles.input} type="text" value={form.who}
                             onChange={(e) => set('who', e.target.value)} placeholder="Name" />
                    </div>
                    <div style={styles.fieldGroup}>
                      <label style={styles.label}>What for?</label>
                      <input style={styles.input} type="text" value={form.what}
                             onChange={(e) => set('what', e.target.value)} placeholder="Category / item" />
                    </div>
                  </div>

                  <div style={styles.splitRow}>
                    <div style={styles.fieldGroup}>
                      <label style={styles.label}>{personNames.person_1} owes</label>
                      <input style={styles.input} type="number" step="0.01" min="0"
                             value={form.person_1_owes}
                             onChange={(e) => set('person_1_owes', parseFloat(e.target.value) || 0)} />
                    </div>
                    <button type="button" style={styles.splitBtn} onClick={split50}>50/50</button>
                    <div style={styles.fieldGroup}>
                      <label style={styles.label}>{personNames.person_2} owes</label>
                      <input style={styles.input} type="number" step="0.01" min="0"
                             value={form.person_2_owes}
                             onChange={(e) => set('person_2_owes', parseFloat(e.target.value) || 0)} />
                    </div>
                  </div>

                  <div style={styles.fieldGroup}>
                    <label style={styles.label}>Notes</label>
                    <textarea style={{ ...styles.input, resize: 'vertical', minHeight: 64 }}
                              value={form.notes} onChange={(e) => set('notes', e.target.value)}
                              placeholder="Optional notes…" />
                  </div>
                </>
            )}
          </div>

          <div style={styles.modalFooter}>
            <button type="button" style={{ ...styles.btn, ...styles.btnSecondary }} onClick={onClose}>Cancel</button>
            <button type="button" style={{ ...styles.btn, ...styles.btnPrimary }} onClick={() => onSave(form)}>Save</button>
          </div>
        </div>
      </Backdrop>
  );
}

// ─── Sync modal ───────────────────────────────────────────────────────────────
function SyncModal({ onSync, onClose }) {
  const pm = prevMonthRange();
  const tm = thisMonthRange();
  const [fromDate, setFromDate] = useState(pm.from);
  const [toDate,   setToDate]   = useState(pm.to);
  const [preset,   setPreset]   = useState('prev');

  const applyPreset = (p) => {
    setPreset(p);
    if (p === 'prev') { setFromDate(pm.from); setToDate(pm.to); }
    if (p === 'this') { setFromDate(tm.from); setToDate(tm.to); }
  };

  return (
      <Backdrop onClose={onClose} zIndex={210}>
        <div style={{ ...styles.modal, maxWidth: 420 }}>
          <div style={styles.modalHeader}>
            <div>
              <div style={styles.modalTitle}>🏦 Sync Bank Transactions</div>
              <div style={styles.modalSub}>Choose a date range to pull from Teller</div>
            </div>
            <button type="button" style={styles.closeBtn} onClick={onClose}>✕</button>
          </div>

          <div style={styles.modalBody}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
              {[
                { key: 'prev', label: 'Previous month' },
                { key: 'this', label: 'This month' },
                { key: 'custom', label: 'Custom range' },
              ].map(({ key, label }) => (
                  <button key={key} type="button"
                          onClick={() => applyPreset(key)}
                          style={{ ...styles.btn, padding: '6px 14px', fontSize: 13,
                            ...(preset === key ? styles.btnPrimary : styles.btnSecondary) }}
                  >
                    {label}
                  </button>
              ))}
            </div>

            <div style={styles.row2}>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>From</label>
                <input style={styles.input} type="date" value={fromDate}
                       onChange={(e) => { setFromDate(e.target.value); setPreset('custom'); }} />
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>To</label>
                <input style={styles.input} type="date" value={toDate}
                       onChange={(e) => { setToDate(e.target.value); setPreset('custom'); }} />
              </div>
            </div>

            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
              Teller returns all transactions; we filter by date client-side — same as{' '}
              <code style={{ color: '#94a3b8' }}>node index.js month</code>.
            </div>
          </div>

          <div style={styles.modalFooter}>
            <button type="button" style={{ ...styles.btn, ...styles.btnSecondary }} onClick={onClose}>Cancel</button>
            <button type="button" style={{ ...styles.btn, ...styles.btnTeller }}
                    onClick={() => onSync(fromDate, toDate)}
                    disabled={!fromDate || !toDate || fromDate > toDate}
            >
              Sync {fromDate} → {toDate}
            </button>
          </div>
        </div>
      </Backdrop>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function SyncToast({ result, onClose }) {
  // Stable ref so the timeout dep never changes and the timer fires exactly once
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });
  useEffect(() => {
    const t = setTimeout(() => onCloseRef.current(), 8000);
    return () => clearTimeout(t);
  }, []); // empty deps — run once on mount, never restarts

  const isCSV = !result.from_date;
  const title = isCSV
      ? `📂 CSV imported — ${result.total_new} transaction${result.total_new !== 1 ? 's' : ''}`
      : `🏦 Sync done — ${result.total_new} new (${result.from_date} → ${result.to_date})`;

  return (
      <div style={styles.toast}>
        <button type="button" onClick={onClose} style={styles.toastClose}>✕</button>
        <div style={{ fontWeight: 600, marginBottom: 6, paddingRight: 24, lineHeight: 1.4 }}>{title}</div>
        {result.details?.map((d, i) => (
            <div key={i} style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
              {d.account || d.token}:{' '}
              {d.error
                  ? `❌ ${d.error}${d.enrollment_status ? ` (${d.enrollment_status})` : ''}`
                  : `${d.new} new / ${d.fetched} fetched`}
            </div>
        ))}
      </div>
  );
}

// ─── Main app ─────────────────────────────────────────────────────────────────
export default function App() {
  const [transactions,  setTransactions]  = useState([]);
  const [personNames,   setPersonNames]   = useState({ person_1: 'Person 1', person_2: 'Person 2' });
  const [loading,       setLoading]       = useState(false);
  const [syncing,       setSyncing]       = useState(false);
  const [sendingSheet,  setSendingSheet]  = useState(false);
  const [uploading,     setUploading]     = useState(false);
  const [error,         setError]         = useState(null);
  const [syncToast,     setSyncToast]     = useState(null);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [selected,      setSelected]      = useState(new Set());
  const [filterSource,  setFilterSource]  = useState('all');
  const [filterShared,  setFilterShared]  = useState('all');
  const [editingTxn,    setEditingTxn]    = useState(null);

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
      setError('Failed to load: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── derived state ──────────────────────────────────────────────────────────
  const visible = transactions.filter((t) => {
    if (filterSource !== 'all' && t.source !== filterSource) return false;
    if (filterShared === 'shared'   && !t.is_shared) return false;
    if (filterShared === 'personal' &&  t.is_shared) return false;
    return true;
  });

  const sharedCount = transactions.filter((t) => t.is_shared).length;
  const sharedTotal = transactions
      .filter((t) => t.is_shared)
      .reduce((s, t) => s + Math.abs(parseFloat(t.amount) || 0), 0);

  // Count how many visible rows are currently selected (for bulk bar display)
  const selectedVisibleCount = visible.filter((t) => selected.has(t.id)).length;
  // Header checkbox is checked only when every visible row is selected
  const allVisibleSelected = visible.length > 0 && visible.every((t) => selected.has(t.id));

  // ── selection ──────────────────────────────────────────────────────────────
  const toggleSelect = useCallback((id) =>
      setSelected((s) => {
        const n = new Set(s);
        n.has(id) ? n.delete(id) : n.add(id);
        return n;
      }), []);

  // Capture visible IDs at call-time to avoid stale-closure bugs
  // wrapped in useCallback — visible in the dep array keeps it fresh but stable
  const toggleAll = useCallback(() => {
    const visibleIds = visible.map((t) => t.id);
    setSelected((s) =>
        visibleIds.every((id) => s.has(id)) ? new Set() : new Set(visibleIds)
    );
  }, [visible]);

  const clearSelection = () => setSelected(new Set());

  // ── actions ────────────────────────────────────────────────────────────────
  const quickMark = useCallback(async (txn, isShared) => {
    const half = parseFloat((Math.abs(parseFloat(txn.amount)) / 2).toFixed(2));
    await axios.put(`${API}/api/transactions/${txn.id}`, {
      is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
      who: txn.who || '', what: txn.what || '', notes: txn.notes || '',
    });
    setTransactions((prev) => prev.map((t) => t.id !== txn.id ? t : {
      ...t, is_shared: isShared,
      person_1_owes: isShared ? half : 0,
      person_2_owes: isShared ? half : 0,
    }));
  }, []);

  const bulkMark = async (isShared) => {
    const ids = visible.filter((t) => selected.has(t.id)).map((t) => t.id);
    if (!ids.length) return;
    await axios.put(`${API}/api/transactions/bulk`, {
      transaction_ids: ids,
      is_shared: isShared,
      split_evenly: true,
    });
    await load();
    clearSelection();
  };

  const saveEdit = async (form) => {
    await axios.put(`${API}/api/transactions/${editingTxn.id}`, form);
    setEditingTxn(null);
    await load();
  };

  const syncTeller = async (fromDate, toDate) => {
    setShowSyncModal(false);
    setSyncing(true);
    try {
      const res = await axios.post(`${API}/api/teller/sync`, { from_date: fromDate, to_date: toDate });
      setSyncToast(res.data);
      await load();
    } catch (e) {
      setError('Teller sync failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSyncing(false);
    }
  };

  const uploadCSV = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    setUploading(true);
    try {
      const res = await axios.post(`${API}/api/upload-csv`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setError(null);
      await load();
      setSyncToast({ total_new: res.data.count, details: [{ account: file.name, new: res.data.count, fetched: res.data.count }] });
    } catch (e) {
      setError('CSV upload failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const sendToSheet = async () => {
    if (!window.confirm(
        `Send ${sharedCount} shared expense${sharedCount !== 1 ? 's' : ''} to Google Sheet? They'll be cleared from the queue.`
    )) return;
    setSendingSheet(true);
    try {
      const res = await axios.post(`${API}/api/send-to-gsheet`);
      await load();
      setSyncToast({ total_new: res.data.count, details: [{ account: 'Google Sheet ✓', new: res.data.count, fetched: res.data.count }] });
    } catch (e) {
      setError('Send failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSendingSheet(false);
    }
  };

  // ── render ─────────────────────────────────────────────────────────────────
  return (
      <div style={styles.root}>

        {/* header */}
        <header style={styles.header}>
          <div style={styles.headerInner}>
            <div style={styles.brand}>
              <span style={styles.brandIcon}>💳</span>
              <span>Expense Tracker</span>
            </div>
            <div style={styles.headerActions}>
              <button type="button"
                      style={{ ...styles.btn, ...styles.btnTeller }}
                      onClick={() => setShowSyncModal(true)}
                      disabled={syncing}
              >
                {syncing ? <><Spin /> Syncing…</> : '🏦 Sync Banks'}
              </button>

              <label style={{ ...styles.btn, ...styles.btnSecondary, cursor: 'pointer', margin: 0 }}>
                {uploading ? <><Spin /> Uploading…</> : '📂 Upload CSV'}
                <input type="file" accept=".csv" hidden onChange={uploadCSV} disabled={uploading} />
              </label>

              <button type="button"
                      style={{ ...styles.btn, ...styles.btnGreen, opacity: sharedCount === 0 ? 0.4 : 1 }}
                      onClick={sendToSheet}
                      disabled={sharedCount === 0 || sendingSheet}
              >
                {sendingSheet ? <Spin /> : '📊'} Send to Sheet{sharedCount > 0 ? ` (${sharedCount})` : ''}
              </button>
            </div>
          </div>
        </header>

        <main style={styles.main}>
          {error && (
              <div style={styles.errorBanner}>
                ⚠️ {error}
                <button type="button" style={styles.toastClose} onClick={() => setError(null)}>✕</button>
              </div>
          )}

          {/* stats */}
          <div style={styles.statsBar}>
            <StatCard label="Total"      value={transactions.length} />
            <StatCard label="Shared"     value={sharedCount}          accent="#10b981" />
            <StatCard label="Shared $"   value={fmt$(sharedTotal)}    accent="#10b981" />
            <StatCard label="Unreviewed" value={transactions.length - sharedCount} accent="#f59e0b" />
          </div>

          {/* toolbar */}
          <div style={styles.toolbar}>
            <div style={styles.filters}>
              <select style={styles.select} value={filterSource} onChange={(e) => setFilterSource(e.target.value)}>
                <option value="all">All sources</option>
                <option value="discover">Discover</option>
                <option value="barclays">Barclays</option>
                <option value="teller">Teller</option>
              </select>
              <select style={styles.select} value={filterShared} onChange={(e) => setFilterShared(e.target.value)}>
                <option value="all">All types</option>
                <option value="shared">Shared only</option>
                <option value="personal">Personal only</option>
              </select>
            </div>

            {/* bulk bar — only shown when ≥1 visible row is selected */}
            {selectedVisibleCount > 0 && (
                <div style={styles.bulkBar}>
                  <span style={styles.bulkCount}>{selectedVisibleCount} selected</span>
                  <button type="button"
                          style={{ ...styles.btn, ...styles.btnGreen, padding: '6px 14px' }}
                          onClick={() => bulkMark(true)}
                  >
                    ✓ Mark shared (50/50)
                  </button>
                  <button type="button"
                          style={{ ...styles.btn, ...styles.btnSecondary, padding: '6px 14px' }}
                          onClick={() => bulkMark(false)}
                  >
                    Mark personal
                  </button>
                  <button type="button"
                          style={{ ...styles.btn, padding: '6px 14px', background: 'transparent', color: '#94a3b8', border: 'none' }}
                          onClick={clearSelection}
                  >
                    Clear
                  </button>
                </div>
            )}
          </div>

          {/* table */}
          <div style={styles.tableWrap}>
            {loading ? (
                <div style={styles.empty}><Spin large /><br />Loading…</div>
            ) : visible.length === 0 ? (
                <div style={styles.empty}>
                  No transactions yet.<br />
                  <span style={{ color: '#94a3b8', fontSize: 14 }}>
                Click <strong>Sync Banks</strong> to pull from Teller, or <strong>Upload CSV</strong> to import a file.
              </span>
                </div>
            ) : (
                <table style={styles.table}>
                  <thead>
                  <tr>
                    <th style={{ ...styles.th, width: 36 }}>
                      <input
                          type="checkbox"
                          checked={allVisibleSelected}
                          onChange={toggleAll}
                          style={{ cursor: 'pointer' }}
                      />
                    </th>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>Description</th>
                    <th style={{ ...styles.th, textAlign: 'right' }}>Amount</th>
                    <th style={styles.th}>Source</th>
                    <th style={styles.th}>Split</th>
                    <th style={styles.th}>Actions</th>
                  </tr>
                  </thead>
                  <tbody>
                  {visible.map((txn) => (
                      <TxnRow
                          key={txn.id}
                          txn={txn}
                          personNames={personNames}
                          isSelected={selected.has(txn.id)}
                          onToggle={toggleSelect}
                          onQuickMark={quickMark}
                          onEdit={() => setEditingTxn(txn)}
                      />
                  ))}
                  </tbody>
                </table>
            )}
          </div>
        </main>

        {showSyncModal && <SyncModal onSync={syncTeller} onClose={() => setShowSyncModal(false)} />}
        {editingTxn    && <EditModal txn={editingTxn} personNames={personNames} onSave={saveEdit} onClose={() => setEditingTxn(null)} />}
        {syncToast     && <SyncToast result={syncToast} onClose={() => setSyncToast(null)} />}
      </div>
  );
}

// ─── Transaction row ──────────────────────────────────────────────────────────
// Note: prop is `isSelected` (not `selected`) to avoid collision with the
// parent's `selected` Set variable in the same scope.
function TxnRow({ txn, personNames, isSelected, onToggle, onQuickMark, onEdit }) {
  const [marking, setMarking] = useState(false);

  const handleMark = async (isShared) => {
    setMarking(true);
    try { await onQuickMark(txn, isShared); } finally { setMarking(false); }
  };

  return (
      <tr style={{
        ...styles.row,
        ...(isSelected ? styles.rowSelected : {}),
        ...(txn.is_shared ? styles.rowShared : {}),
      }}>
        <td style={styles.td}>
          <input type="checkbox" checked={isSelected} onChange={() => onToggle(txn.id)} style={{ cursor: 'pointer' }} />
        </td>
        <td style={{ ...styles.td, color: '#94a3b8', whiteSpace: 'nowrap', fontSize: 13 }}>
          {fmtDate(txn.date)}
        </td>
        <td style={styles.td}>
          <div style={{ fontWeight: 500 }}>{txn.description}</div>
          {txn.is_shared && txn.what && <div style={{ fontSize: 12, color: '#10b981' }}>{txn.what}</div>}
          {txn.notes && <div style={{ fontSize: 12, color: '#64748b' }}>{txn.notes}</div>}
        </td>
        <td style={{ ...styles.td, textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
          {fmt$(txn.amount)}
        </td>
        <td style={styles.td}>
        <span style={{ ...styles.badge, background: SOURCE_COLOR[txn.source] || '#6b7280' }}>
          {txn.source}
        </span>
        </td>
        <td style={styles.td}>
          {txn.is_shared ? (
              <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                <span style={styles.sharedBadge}>shared</span>
                <div style={{ color: '#94a3b8', marginTop: 2 }}>
                  {personNames.person_1}: {fmt$(txn.person_1_owes || 0)}<br />
                  {personNames.person_2}: {fmt$(txn.person_2_owes || 0)}
                </div>
              </div>
          ) : (
              <span style={styles.personalBadge}>personal</span>
          )}
        </td>
        <td style={styles.td}>
          <div style={styles.actionGroup}>
            <div style={styles.inlineToggle}>
              <button type="button"
                      disabled={marking || !txn.is_shared}
                      onClick={() => handleMark(false)}
                      style={{ ...styles.toggleBtn, ...(!txn.is_shared ? styles.toggleBtnActivePersonal : {}) }}
              >
                Personal
              </button>
              <button type="button"
                      disabled={marking || txn.is_shared}
                      onClick={() => handleMark(true)}
                      style={{ ...styles.toggleBtn, ...(txn.is_shared ? styles.toggleBtnActiveShared : {}) }}
              >
                50/50
              </button>
            </div>
            <button type="button" style={styles.editBtn} onClick={onEdit}>Edit</button>
          </div>
        </td>
      </tr>
  );
}

// ─── Small components ─────────────────────────────────────────────────────────
function StatCard({ label, value, accent }) {
  return (
      <div style={styles.statCard}>
        <div style={{ ...styles.statVal, color: accent || '#f1f5f9' }}>{value}</div>
        <div style={styles.statLabel}>{label}</div>
      </div>
  );
}

function Spin({ large }) {
  return (
      <span style={{
        display: 'inline-block',
        width: large ? 28 : 14, height: large ? 28 : 14,
        border: '2px solid rgba(255,255,255,0.25)',
        borderTopColor: '#fff',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
        verticalAlign: 'middle',
      }} />
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = {
  root: { minHeight: '100vh', background: '#0f172a', color: '#f1f5f9', fontFamily: "'DM Sans', system-ui, sans-serif" },

  header:        { background: '#1e293b', borderBottom: '1px solid #334155', position: 'sticky', top: 0, zIndex: 100 },
  headerInner:   { maxWidth: 1280, margin: '0 auto', padding: '12px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 },
  brand:         { display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700, fontSize: 18, letterSpacing: '-0.3px' },
  brandIcon:     { fontSize: 22 },
  headerActions: { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' },

  btn:           { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 600, lineHeight: 1.4 },
  btnTeller:     { background: '#0d9488', color: '#fff' },
  btnGreen:      { background: '#10b981', color: '#fff' },
  btnSecondary:  { background: '#334155', color: '#f1f5f9' },
  btnPrimary:    { background: '#3b82f6', color: '#fff' },

  main: { maxWidth: 1280, margin: '0 auto', padding: '24px' },

  errorBanner: { background: '#7f1d1d', border: '1px solid #991b1b', borderRadius: 8, padding: '12px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 },

  statsBar:  { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 },
  statCard:  { background: '#1e293b', borderRadius: 10, padding: '16px 20px', border: '1px solid #334155' },
  statVal:   { fontSize: 26, fontWeight: 700, letterSpacing: '-0.5px' },
  statLabel: { fontSize: 12, color: '#64748b', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' },

  toolbar:   { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' },
  filters:   { display: 'flex', gap: 10 },
  select:    { background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9', borderRadius: 8, padding: '8px 12px', fontSize: 14, cursor: 'pointer' },

  bulkBar:   { display: 'flex', alignItems: 'center', gap: 8, background: '#1e3a5f', border: '1px solid #2563eb', borderRadius: 8, padding: '6px 12px', flexWrap: 'wrap' },
  bulkCount: { fontWeight: 700, fontSize: 14, color: '#93c5fd', marginRight: 4 },

  tableWrap:   { background: '#1e293b', borderRadius: 12, border: '1px solid #334155', overflow: 'hidden' },
  table:       { width: '100%', borderCollapse: 'collapse' },
  th:          { padding: '10px 14px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #334155', background: '#0f172a' },
  row:         { borderBottom: '1px solid #1e293b', transition: 'background 0.1s' },
  rowSelected: { background: '#1e3a5f' },
  rowShared:   { background: 'rgba(16,185,129,0.06)' },
  td:          { padding: '12px 14px', fontSize: 14, verticalAlign: 'middle' },

  badge:         { display: 'inline-block', padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 700, color: '#fff', textTransform: 'uppercase', letterSpacing: '0.04em' },
  sharedBadge:   { display: 'inline-block', padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 700, background: 'rgba(16,185,129,0.2)', color: '#10b981', textTransform: 'uppercase' },
  personalBadge: { display: 'inline-block', padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: '#1e293b', color: '#64748b', border: '1px solid #334155' },

  actionGroup:             { display: 'flex', alignItems: 'center', gap: 6 },
  inlineToggle:            { display: 'flex', borderRadius: 6, overflow: 'hidden', border: '1px solid #334155' },
  toggleBtn:               { padding: '5px 10px', border: 'none', background: '#0f172a', color: '#64748b', cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  toggleBtnActivePersonal: { background: '#334155', color: '#f1f5f9' },
  toggleBtnActiveShared:   { background: '#10b981', color: '#fff' },
  editBtn:                 { padding: '5px 10px', border: '1px solid #334155', background: 'transparent', color: '#94a3b8', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600 },

  empty: { padding: '60px 20px', textAlign: 'center', color: '#475569', fontSize: 16, lineHeight: 2.2 },

  modal:       { background: '#1e293b', borderRadius: 14, border: '1px solid #334155', width: '100%', maxWidth: 520, boxShadow: '0 24px 60px rgba(0,0,0,0.6)', maxHeight: '90vh', overflowY: 'auto' },
  modalHeader: { padding: '20px 24px 16px', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  modalTitle:  { fontWeight: 700, fontSize: 16 },
  modalSub:    { color: '#64748b', fontSize: 13, marginTop: 2 },
  closeBtn:    { flexShrink: 0, background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: 4 },
  modalBody:   { padding: '20px 24px' },
  modalFooter: { padding: '16px 24px', borderTop: '1px solid #334155', display: 'flex', justifyContent: 'flex-end', gap: 10 },

  toggleRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
  segmented: { display: 'flex', borderRadius: 8, overflow: 'hidden', border: '1px solid #334155' },
  seg:       { padding: '8px 20px', border: 'none', background: '#0f172a', color: '#64748b', cursor: 'pointer', fontSize: 14, fontWeight: 600 },
  segActive: { background: '#3b82f6', color: '#fff' },

  row2:       { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 },
  splitRow:   { display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 10, alignItems: 'flex-end', marginBottom: 16 },
  splitBtn:   { padding: '9px 12px', background: '#334155', border: 'none', color: '#f1f5f9', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' },
  fieldGroup: { display: 'flex', flexDirection: 'column', gap: 6 },
  label:      { fontSize: 12, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' },
  input:      { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '9px 12px', color: '#f1f5f9', fontSize: 14, outline: 'none', width: '100%', boxSizing: 'border-box' },

  toast:      { position: 'fixed', bottom: 24, right: 24, background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: '16px 20px 14px', maxWidth: 380, boxShadow: '0 8px 30px rgba(0,0,0,0.5)', zIndex: 300 },
  toastClose: { position: 'absolute', top: 10, right: 12, background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16, lineHeight: 1 },
};

const _ss = document.createElement('style');
_ss.textContent = [
  '@keyframes spin { to { transform: rotate(360deg); } }',
  'input[type=date]::-webkit-calendar-picker-indicator { filter: invert(0.6); cursor: pointer; }',
].join('\n');
document.head.appendChild(_ss);