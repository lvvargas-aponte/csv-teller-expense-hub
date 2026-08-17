import React from 'react';
import Spin from '../../ui/Spin';

/**
 * The shell every dashboard card renders into.
 *
 * `index` and `kicker` carry the dashboard's narrative arc — a section
 * number and an eyebrow line, so the grid reads as an argument rather than
 * a pile of widgets. Every caller has passed them since the cards were
 * written; they were silently dropped here until the grid made them visible.
 *
 * `onHide` is only supplied while the dashboard is in edit mode, so the
 * remove control appears exactly when it is actionable.
 */
export default function DashboardCard({
  title,
  index,
  kicker,
  loading,
  error,
  empty,
  emptyText,
  children,
  headerExtra,
  onHide,
}) {
  return (
    <div className="finances-section dashboard-card">
      <div className="eh-dcard-head">
        <div className="eh-dcard-heading">
          {kicker && (
            <div className="eh-dcard-kicker">
              {index !== undefined && index !== null && (
                <span className="eh-dcard-index">{String(index).padStart(2, '0')}</span>
              )}
              {kicker}
            </div>
          )}
          <h3 className="finances-section-title" style={{ margin: 0 }}>{title}</h3>
        </div>
        <div className="eh-dcard-head-right">
          {headerExtra}
          {onHide && (
            <button
              type="button"
              className="eh-dcard-hide"
              onClick={onHide}
              title={`Remove ${title} from the dashboard`}
              aria-label={`Remove ${title} from the dashboard`}
            >
              ×
            </button>
          )}
        </div>
      </div>
      <div className="eh-dcard-body">
        {loading && (
          <div className="eh-dcard-state"><Spin /> Loading…</div>
        )}
        {error && !loading && (
          <div className="eh-dcard-state eh-dcard-state--error">{error}</div>
        )}
        {empty && !loading && !error && (
          <div className="eh-dcard-state eh-dcard-state--empty">
            {emptyText || 'No data yet.'}
          </div>
        )}
        {!loading && !error && !empty && children}
      </div>
    </div>
  );
}
