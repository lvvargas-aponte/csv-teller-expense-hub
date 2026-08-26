import React, { useEffect } from 'react';

const TOAST_DURATION_MS = 8000;

export default function SyncToast({ result, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, TOAST_DURATION_MS);
    return () => clearTimeout(t);
  }, [onClose]);

  // A sync/send failure whose page has since unmounted (SyncContext no-ops
  // the page's own setError once it's gone) still needs to surface — this
  // shell-level toast is the one thing that survives navigation.
  if (result.error) {
    return (
      <div className="toast toast--error" data-testid="sync-toast">
        <button type="button" onClick={onClose} className="toast-close">✕</button>
        <div className="toast-title">⚠️ Sync failed</div>
        <div className="toast-detail">{result.error}</div>
      </div>
    );
  }

  const isCSV = !result.from_date;
  const title = isCSV
    ? `📂 CSV imported — ${result.total_new} transaction${result.total_new !== 1 ? 's' : ''}`
    : `🏦 Sync done — ${result.total_new} new (${result.from_date} → ${result.to_date})`;

  return (
    <div className="toast" data-testid="sync-toast">
      <button type="button" onClick={onClose} className="toast-close">✕</button>
      <div className="toast-title">{title}</div>
      {result.details?.map((d, i) => (
        <div key={i} className="toast-detail">
          {d.account || d.token}:{' '}
          {d.error
            ? `❌ ${d.error}${d.enrollment_status ? ` (${d.enrollment_status})` : ''}`
            : `${d.new} new / ${d.fetched} fetched`}
        </div>
      ))}
    </div>
  );
}
