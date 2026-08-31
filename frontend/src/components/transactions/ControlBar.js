import React from 'react';
import { fmt$ } from '../../utils/formatting';
import Spin from '../ui/Spin';

export default function ControlBar({
  totalCount,
  sharedCount,
  sharedAmt,
  unreviewedCount,
  uploading,
  dedupingNow,
  onPickCsv,
  onFindDuplicates,
}) {
  return (
    <div className="tx-control-bar">
      <div className="tx-stat-pills">
        <div className="tx-stat-pill">
          <strong>{totalCount}</strong>
          <span>total</span>
        </div>
        <div className="tx-stat-pill">
          <span className="tx-pill-dot" style={{ background: 'var(--good)' }} />
          <strong className="tx-green">{sharedCount}</strong>
          <span>shared</span>
          <strong className="tx-green">{fmt$(sharedAmt)}</strong>
        </div>
        <div className="tx-stat-pill" data-testid="stat-pill-unreviewed">
          <span className="tx-pill-dot" style={{ background: 'var(--warn)' }} />
          <strong className="tx-amber">{unreviewedCount}</strong>
          <span>unreviewed</span>
        </div>
      </div>

      <div className="tx-control-spacer" />

      <div className="tx-action-row">
        <label className="tx-btn tx-btn-secondary" style={{ cursor: 'pointer' }}>
          {uploading ? <><Spin /> Uploading…</> : <>↑ Upload CSV</>}
          <input
            type="file"
            accept=".csv"
            hidden
            onChange={onPickCsv}
            disabled={uploading}
          />
        </label>
        {onFindDuplicates && (
          <button
            type="button"
            className="tx-btn tx-btn-secondary"
            onClick={onFindDuplicates}
            disabled={dedupingNow}
            title="Find and remove duplicate transactions"
          >
            {dedupingNow ? <><Spin /> Checking…</> : <>⎘ Find duplicates</>}
          </button>
        )}
      </div>
    </div>
  );
}
