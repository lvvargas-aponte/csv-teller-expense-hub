import React from 'react';
import { AlertIcon, CheckIcon } from './icons';

function formatTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d) ? null : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * The one line that replaces the sync strip, the refusal banner and the
 * success toast. Only the most recent thing that happened is worth a line, so
 * a message from the sync just run outranks the stored last-run summary.
 */
export default function SyncStatusLine({ status, syncMessage, onDismissMessage, onSync, syncing }) {
  if (syncMessage && syncMessage.kind === 'ok') {
    return (
      <div className="sh-status" role="status">
        <span className="sh-lead"><CheckIcon /> Synced</span>
        <span className="sh-sep">·</span>
        <span>{syncMessage.text}</span>
      </div>
    );
  }

  if (syncMessage) {
    return (
      <div className="sh-status sh-status--warn" role="alert">
        <span className="sh-lead">
          <AlertIcon size={13} />
          {syncMessage.kind === 'refused' ? 'Sync refused' : 'Sync failed'}
        </span>
        <span className="sh-sep">·</span>
        <span>{syncMessage.text}</span>
        <button
          type="button"
          className="sh-status-link"
          onClick={onDismissMessage}
        >Dismiss sync message</button>
      </div>
    );
  }

  if (!status) return null;
  const { last_run: lastRun, refusal } = status;

  if (refusal) {
    return (
      <div className="sh-status sh-status--warn" role="alert">
        <span className="sh-lead"><AlertIcon size={13} /> Sync refused</span>
        <span className="sh-sep">·</span>
        <span>{refusal.message || refusal.reason}</span>
      </div>
    );
  }

  if (!lastRun) {
    return (
      <div className="sh-status">
        <span>No sync has run yet this month.</span>
        <button type="button" className="sh-status-link" onClick={onSync} disabled={syncing}>
          Sync now
        </button>
      </div>
    );
  }

  const at = formatTime(lastRun.finished_at || lastRun.started_at);
  const clean = lastRun.status === 'ok';

  return (
    <div className={`sh-status${clean ? '' : ' sh-status--warn'}`}>
      <span className="sh-lead">
        {clean ? <CheckIcon /> : <AlertIcon size={13} />}
        {clean ? 'Synced' : `Sync ${lastRun.status}`}{at ? ` ${at}` : ''}
      </span>
      <span className="sh-sep">·</span>
      <span>{lastRun.rows_pushed} rows sent, {lastRun.rows_pulled} received</span>
    </div>
  );
}
