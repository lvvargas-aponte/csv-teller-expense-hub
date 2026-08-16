import React, { useState } from 'react';
import Spin from '../../ui/Spin';
import { AprCell, AprLegend } from './AprCell';
import { fmt$, fmtDate, fmtSigned } from '../../../utils/formatting';
import { deferredPlan, fmtMonths, hasAssetValue, rowEquity } from './helpers';
import PayoffProgress from './PayoffProgress';

const DEBT_CLASSES = [
  { id: 'credit_card', label: '💳 Credit Card' },
  { id: 'loan',         label: '🏠 Loan' },
  { id: 'other',        label: 'Other' },
];

export default function PayoffForm({
  revolvingRows = [], securedRows = [],
  allAccounts = [], detailsVersion = 0, strategy, extra, error, loading, orderById,
  onSetRow, onPersistApr, onPersistMinPayment, onPersistDetail, onAddRow, onRemoveRow,
  onStrategyChange, onExtraChange, onCalculate,
}) {
  const [expanded, setExpanded] = useState(() => new Set());
  const toggleExpanded = (id) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  // Everything a section needs to render a row identically in either table.
  const rowProps = {
    allAccounts, detailsVersion, strategy, orderById, expanded, toggleExpanded,
    onSetRow, onPersistApr, onPersistMinPayment, onPersistDetail, onRemoveRow,
  };

  return (
    <>
      <div className="ov-strategy-row">
        <span className="ov-strategy-label">Strategy</span>
        <div className="ov-strategy-tabs">
          <button
            type="button"
            className={`ov-strategy-tab${strategy === 'avalanche' ? ' ov-strategy-tab--active' : ''}`}
            onClick={() => onStrategyChange('avalanche')}
          >🔥 Avalanche — High APR first</button>
          <button
            type="button"
            className={`ov-strategy-tab${strategy === 'snowball' ? ' ov-strategy-tab--active' : ''}`}
            onClick={() => onStrategyChange('snowball')}
          >❄️ Snowball — Low balance first</button>
        </div>
      </div>

      <DebtSection
        title="💳 Cards & unsecured debt"
        note="Ranked by the strategy above — this is the queue your extra payment feeds."
        rows={revolvingRows}
        showAprLegend
        emptyMessage={<>No unsecured debt yet. Click <strong>+ Add debt</strong> below to get started.</>}
        {...rowProps}
      />

      <button type="button" className="ov-btn ov-btn-ghost ov-btn-sm" onClick={onAddRow}>
        + Add debt
      </button>

      {securedRows.length > 0 && (
        <DebtSection
          title="🏠 Loans & secured debt"
          note="Backed by an asset, so these sit out of the payoff queue — ranking on APR alone would send your extra payment to a mortgage ahead of a 29% card. Edits here still save."
          rows={securedRows}
          secured
          {...rowProps}
        />
      )}

      <div className="ov-extra-row">
        <label className="ov-extra-label" htmlFor="payoff-extra-input">
          Extra monthly payment toward cards
        </label>
        <div className="ov-extra-input-wrap">
          <span>$</span>
          <input
            id="payoff-extra-input"
            type="number" min="0" step="10" placeholder="0"
            value={extra}
            onChange={(e) => onExtraChange(e.target.value)}
            aria-label="Extra monthly payment"
          />
        </div>
      </div>

      {error && <div className="ov-error">{error}</div>}

      <div className="ov-action-row">
        <button
          type="button"
          className="ov-btn ov-btn-primary"
          onClick={onCalculate}
          disabled={loading || revolvingRows.length === 0}
        >
          {loading ? <><Spin /> Calculating…</> : 'Calculate payoff timeline →'}
        </button>
      </div>
    </>
  );
}

// One table of debts. Rendered twice — once for the queued unsecured rows,
// once for secured ones. `secured` only changes the trimmings: no order badge
// (those rows aren't in the queue to be numbered), plus an equity read-out.
function DebtSection({
  title, note, rows, secured = false, showAprLegend = false, emptyMessage,
  allAccounts, detailsVersion, strategy, orderById, expanded, toggleExpanded,
  onSetRow, onPersistApr, onPersistMinPayment, onPersistDetail, onRemoveRow,
}) {
  const total = rows.reduce((s, r) => s + (parseFloat(r.balance) || 0), 0);

  return (
    <section className={`ov-debt-section${secured ? ' ov-debt-section--secured' : ''}`}>
      <div className="ov-debt-section-head">
        <span className="ov-debt-section-title">{title}</span>
        <span className="ov-debt-section-total">{fmt$(total)}</span>
        {secured && <span className="ov-debt-section-tag">Not in the payoff queue</span>}
      </div>
      {note && <p className="ov-debt-section-note">{note}</p>}

      <div className="ov-debt-table-wrap">
        <table className="ov-debt-table">
          <thead>
            <tr>
              <th style={{ width: 28 }}></th>
              <th style={{ width: 24 }}></th>
              <th>Account</th>
              <th style={{ width: 130 }}>Balance</th>
              <th style={{ width: 120 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end' }}>
                  APR %
                  {showAprLegend && <AprLegend />}
                </div>
              </th>
              <th style={{ width: 140 }}>Min Payment</th>
              <th style={{ width: 36 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: '24px 14px', color: '#6b7280', fontSize: 13, textAlign: 'center' }}>
                  {emptyMessage}
                </td>
              </tr>
            ) : rows.map((r, idx) => {
              const order = orderById.get(r._id);
              const isOpen = expanded.has(r._id);
              // The strategy is part of the key on purpose: switching strategies
              // re-mounts each row so the entrance animation re-plays in the
              // new sort order.
              return (
                <React.Fragment key={`${strategy}-${r._id}`}>
                  <tr className="ov-row-animate" style={{ animationDelay: `${idx * 0.04}s` }}>
                    <td style={{ textAlign: 'center', paddingRight: 4 }}>
                      {secured ? (
                        <span className="ov-secured-mark" title="Secured by an asset — outside the payoff queue">🏠</span>
                      ) : order ? (
                        <span className="ov-order-badge">{order}</span>
                      ) : (
                        <span style={{ display: 'inline-block', width: 20 }} />
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className={`ov-expand-toggle${isOpen ? ' ov-expand-toggle--open' : ''}`}
                        onClick={() => toggleExpanded(r._id)}
                        aria-label={isOpen ? 'Hide debt details' : 'Show debt details'}
                        aria-expanded={isOpen}
                        title="Class, asset value, due date, deferred interest"
                      >›</button>
                    </td>
                    <td>
                      <input
                        className="ov-debt-input"
                        type="text"
                        placeholder="Account name"
                        value={r.name}
                        onChange={(e) => onSetRow(r._id, 'name', e.target.value)}
                      />
                      {secured && <EquityChip row={r} onAddValue={() => toggleExpanded(r._id)} />}
                    </td>
                    <td>
                      <div className="ov-debt-input-wrap">
                        <span className="ov-debt-input-prefix">$</span>
                        <input
                          className="ov-debt-input ov-num"
                          type="number" min="0" step="0.01" placeholder="0.00"
                          value={r.balance}
                          onChange={(e) => onSetRow(r._id, 'balance', e.target.value)}
                        />
                      </div>
                    </td>
                    <td>
                      <AprCell
                        value={r.apr}
                        onChange={(v) => { onSetRow(r._id, 'apr', v); onPersistApr?.(r._id, v); }}
                      />
                    </td>
                    <td>
                      <div className="ov-debt-input-wrap">
                        <span className="ov-debt-input-prefix">$</span>
                        <input
                          className="ov-debt-input ov-num"
                          type="number" min="0" step="0.01" placeholder="0.00"
                          value={r.min_payment}
                          onChange={(e) => onSetRow(r._id, 'min_payment', e.target.value)}
                          onBlur={(e) => onPersistMinPayment?.(r._id, e.target.value)}
                        />
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className="ov-icon-btn ov-icon-btn--danger"
                        onClick={() => onRemoveRow(r._id)}
                        aria-label="Remove debt"
                        title="Remove"
                      >✕</button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="ov-debt-detail-row">
                      <td colSpan={7}>
                        <DebtDetailPanel
                          row={r}
                          allAccounts={allAccounts}
                          detailsVersion={detailsVersion}
                          onSetRow={onSetRow}
                          onPersistDetail={onPersistDetail}
                        />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// Equity on the collapsed row, so a secured debt shows what it's actually
// worth without expanding. With no market value on file there's nothing to
// compute, so it points at the field that supplies one.
function EquityChip({ row, onAddValue }) {
  if (!hasAssetValue(row)) {
    return (
      <button type="button" className="ov-equity-hint" onClick={onAddValue}>
        + add asset value for equity
      </button>
    );
  }
  const equity = rowEquity(row);
  return (
    <span className={`ov-equity-chip ${equity >= 0 ? 'ov-equity-badge--pos' : 'ov-equity-badge--neg'}`}>
      Equity {fmtSigned(equity)}
    </span>
  );
}

function DebtDetailPanel({ row, allAccounts = [], detailsVersion = 0, onSetRow, onPersistDetail }) {
  const update = (key, backendKey, val) => {
    onSetRow(row._id, key, val);
    onPersistDetail?.(row._id, { [backendKey]: val });
  };

  const equity = rowEquity(row);

  return (
    <div className="ov-debt-detail-panel">
      <div className="ov-debt-detail-field">
        <span className="ov-debt-detail-label">Debt type</span>
        <div className="ov-class-tabs">
          {DEBT_CLASSES.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`ov-class-tab${row.debtClass === c.id ? ' ov-class-tab--active' : ''}`}
              onClick={() => update('debtClass', 'debt_class', c.id)}
            >{c.label}</button>
          ))}
        </div>
      </div>

      {row.debtClass === 'loan' && (
        <div className="ov-debt-detail-field">
          <span className="ov-debt-detail-label">Asset value</span>
          <div className="ov-debt-input-wrap">
            <span className="ov-debt-input-prefix">$</span>
            <input
              className="ov-debt-input ov-num"
              type="number" min="0" step="100" placeholder="Current market value"
              value={row.assetValue}
              onChange={(e) => onSetRow(row._id, 'assetValue', e.target.value)}
              onBlur={(e) => onPersistDetail?.(row._id, { asset_value: e.target.value === '' ? null : parseFloat(e.target.value) })}
            />
          </div>
          {hasAssetValue(row) && (
            <span className={`ov-equity-badge ${equity >= 0 ? 'ov-equity-badge--pos' : 'ov-equity-badge--neg'}`}>
              Equity {fmtSigned(equity)}
            </span>
          )}
        </div>
      )}

      <div className="ov-debt-detail-field">
        <span className="ov-debt-detail-label">Due date</span>
        <input
          className="ov-debt-input"
          type="date"
          value={row.dueDate}
          onChange={(e) => update('dueDate', 'due_date', e.target.value)}
        />
      </div>

      <div className="ov-debt-detail-field ov-debt-detail-field--wide">
        <label className="ov-debt-detail-checkbox">
          <input
            type="checkbox"
            checked={row.deferredInterest}
            onChange={(e) => update('deferredInterest', 'deferred_interest', e.target.checked)}
          />
          Deferred interest promo
        </label>
        {row.deferredInterest && (
          <>
            <div className="ov-promo-fields">
              <div>
                <span className="ov-debt-detail-label">Promo APR %</span>
                <input
                  className="ov-debt-input ov-num"
                  type="number" min="0" step="0.01" placeholder="0"
                  value={row.promoApr}
                  onChange={(e) => onSetRow(row._id, 'promoApr', e.target.value)}
                  onBlur={(e) => onPersistDetail?.(row._id, { promo_apr: e.target.value === '' ? null : parseFloat(e.target.value) })}
                />
              </div>
              <div>
                <span className="ov-debt-detail-label" title="Any balance left on this date triggers the deferred interest charge">
                  Pay in full by
                </span>
                <input
                  className="ov-debt-input"
                  type="date"
                  value={row.promoExpires}
                  onChange={(e) => update('promoExpires', 'promo_expires', e.target.value)}
                />
              </div>
            </div>

            <div className="ov-promo-fields">
              <div>
                <span className="ov-debt-detail-label">Paying minimum from</span>
                <input
                  className="ov-debt-input"
                  type="date"
                  value={row.minPaymentFrom}
                  onChange={(e) => update('minPaymentFrom', 'min_payment_from', e.target.value)}
                />
              </div>
              <div>
                <span className="ov-debt-detail-label" title="After this date you switch to the catch-up payment below">
                  Through
                </span>
                <input
                  className="ov-debt-input"
                  type="date"
                  value={row.minPaymentUntil}
                  onChange={(e) => update('minPaymentUntil', 'min_payment_until', e.target.value)}
                />
              </div>
            </div>

            <DeferredPlanCallout row={row} />
          </>
        )}
      </div>

      {row.accountId && (
        <div className="ov-debt-detail-field ov-debt-detail-field--full">
          <span className="ov-debt-detail-label">Payoff tracking</span>
          <div className="ov-promo-fields">
            <div>
              <span className="ov-debt-detail-label">Starting balance</span>
              <div className="ov-debt-input-wrap">
                <span className="ov-debt-input-prefix">$</span>
                <input
                  className="ov-debt-input ov-num"
                  type="number" min="0" step="0.01" placeholder="What you owed at the start"
                  value={row.payoffStartBalance}
                  onChange={(e) => onSetRow(row._id, 'payoffStartBalance', e.target.value)}
                  onBlur={(e) => onPersistDetail?.(row._id, {
                    payoff_start_balance: e.target.value === '' ? null : parseFloat(e.target.value),
                  })}
                />
              </div>
            </div>
            <div>
              <span className="ov-debt-detail-label" title="Payments before this date are left out of the totals">
                Tracking since
              </span>
              <input
                className="ov-debt-input"
                type="date"
                value={row.payoffStartDate}
                onChange={(e) => update('payoffStartDate', 'payoff_start_date', e.target.value)}
              />
            </div>
            <div>
              <span className="ov-debt-detail-label" title="Used to find the outgoing side of each payment">
                Paying from
              </span>
              <select
                className="ov-debt-input"
                value={row.paymentAccountId}
                onChange={(e) => update('paymentAccountId', 'payment_account_id', e.target.value)}
              >
                <option value="">— pick an account —</option>
                {allAccounts
                  .filter((a) => a.id !== row.accountId)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {`${a.institution || ''} ${a.name || ''}`.trim() || a.id}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          <PayoffProgress row={row} detailsVersion={detailsVersion} />
        </div>
      )}
    </div>
  );
}

// What the deadline actually costs per month, given the minimum-only stretch
// the user described. Silent until there's a balance and a deadline to work
// with — a half-filled promo shouldn't shout numbers.
function DeferredPlanCallout({ row }) {
  const plan = deferredPlan(row);
  if (!plan) return null;

  if (plan.expired) {
    return (
      <div className="ov-promo-warning">
        ⚠️ The {fmtDate(row.promoExpires)} deadline has passed with {fmt$(plan.balance)} still
        owing — deferred interest at {row.apr || '—'}% has likely already been billed.
      </div>
    );
  }

  return (
    <div className="ov-promo-plan">
      <div className="ov-promo-plan-line">
        {plan.minMonths > 0 ? (
          <>
            Paying the {fmt$(parseFloat(row.min_payment) || 0)} minimum for {fmtMonths(plan.minMonths)} leaves{' '}
            <strong>{fmt$(plan.balanceAtWindowEnd)}</strong> against a {fmtDate(row.promoExpires)} deadline.
          </>
        ) : (
          <>
            <strong>{fmt$(plan.balance)}</strong> has to reach zero by {fmtDate(row.promoExpires)}.
          </>
        )}
      </div>

      {plan.balanceAtWindowEnd > 0 && (
        <div className="ov-promo-plan-line">
          {plan.lumpSum ? (
            <>That whole <strong>{fmt$(plan.balanceAtWindowEnd)}</strong> falls due as one payment —
            the minimum-payment window runs right up to the deadline, leaving no months to catch up.</>
          ) : (
            <>Clearing it needs <strong className="ov-promo-plan-figure">{fmt$(plan.requiredMonthly)}/mo</strong>{' '}
            for the final {fmtMonths(plan.catchUpMonths)}.</>
          )}
        </div>
      )}

      {!plan.minCoversInterest && (
        <div className="ov-promo-plan-line ov-promo-plan-line--warn">
          The minimum doesn't cover the monthly interest, so the balance grows while you pay it.
        </div>
      )}

      {!plan.clearedByMinimums && plan.retroInterest > 0 && (
        <div className="ov-promo-plan-line ov-promo-plan-line--warn">
          Miss it and roughly {fmt$(plan.retroInterest)} of deferred interest is billed back at
          once — that estimate only counts from today forward, so the real charge reaches further back.
        </div>
      )}
    </div>
  );
}
