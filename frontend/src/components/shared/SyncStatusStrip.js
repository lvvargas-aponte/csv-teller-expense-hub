import React from 'react';

function formatTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d) ? null : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function SyncStatusStrip({ status }) {
  if (!status) return null;
  const { last_run: lastRun, refusal } = status;

  return (
    <div className="shared-status-strip">
      {lastRun ? (
        <span className="shared-status-line">
          Last sync {formatTime(lastRun.finished_at || lastRun.started_at) || ''}{' '}
          {lastRun.status === 'ok' ? (
            <span className="shared-status-ok">
              <span aria-hidden="true">✓</span> success
              {' · '}{lastRun.rows_pushed} sent, {lastRun.rows_pulled} received
            </span>
          ) : (
            <span className="shared-status-warn">
              <span aria-hidden="true">⚠</span> {lastRun.status}
            </span>
          )}
        </span>
      ) : (
        <span className="shared-status-line">No sync has run yet.</span>
      )}
      {refusal && (
        <span className="shared-status-refusal" role="alert">
          <span aria-hidden="true">⚠</span> Sync refused — {refusal.reason}
        </span>
      )}
    </div>
  );
}
