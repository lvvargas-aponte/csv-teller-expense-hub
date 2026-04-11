import React, { useEffect } from 'react';

const TOAST_DURATION_MS = 8000;

export default function SyncToast({ result, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, TOAST_DURATION_MS);
    return () => clearTimeout(t);
  }, [onClose]);

  const isCSV = !result.from_date;
  const title = isCSV
    ? `📂 CSV imported — ${result.total_new} transaction${result.total_new !== 1 ? 's' : ''}`
    : `🏦 Sync done — ${result.total_new} new (${result.from_date} → ${result.to_date})`;

  return (
    <div className="toast">
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
