import React from 'react';
import Spin from '../../ui/Spin';
import { AprCell, AprLegend } from './AprCell';

export default function PayoffForm({
  rows, strategy, extra, error, loading, orderById,
  onSetRow, onPersistApr, onAddRow, onRemoveRow,
  onStrategyChange, onExtraChange, onCalculate,
}) {
  return (
    <>
      <div className="ov-strategy-row">
        <span className="ov-strategy-label">Strategy</span>
        <div className="ov-strategy-tabs">
          <button
            type="button"
            className={`ov-strategy-tab${strategy === 'avalanche' ? ' ov-strategy-tab--active' : ''}`}
            onClick={() => onStrategyChange('avalanche')}
          ><span aria-hidden="true">🔥</span> Avalanche — High APR first</button>
          <button
            type="button"
            className={`ov-strategy-tab${strategy === 'snowball' ? ' ov-strategy-tab--active' : ''}`}
            onClick={() => onStrategyChange('snowball')}
          ><span aria-hidden="true">❄️</span> Snowball — Low balance first</button>
        </div>
      </div>

      <div className="ov-debt-table-wrap">
        <table className="ov-debt-table eh-table">
          <caption className="sr-only">Debts in the payoff plan</caption>
          <thead>
            <tr>
              <th scope="col" style={{ width: 28 }}><span className="sr-only">Include</span></th>
              <th scope="col">Account</th>
              <th scope="col" style={{ width: 130 }}>Balance</th>
              <th scope="col" style={{ width: 120 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end' }}>
                  APR %
                  <AprLegend />
                </div>
              </th>
              <th scope="col" style={{ width: 140 }}>Min Payment</th>
              <th scope="col" style={{ width: 36 }}><span className="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '24px 14px', color: 'var(--text-muted)', fontSize: 13, textAlign: 'center' }}>
                  No debts yet. Click <strong>+ Add debt</strong> below to get started.
                </td>
              </tr>
            ) : rows.map((r, idx) => {
              const order = orderById.get(r._id);
              // The strategy is part of the key on purpose: switching strategies
              // re-mounts each row so the entrance animation re-plays in the
              // new sort order.
              return (
                <tr key={`${strategy}-${r._id}`} className="ov-row-animate"
                    style={{ animationDelay: `${idx * 0.04}s` }}>
                  <td style={{ textAlign: 'center', paddingRight: 4 }}>
                    {order ? <span className="ov-order-badge">{order}</span> : <span style={{ display: 'inline-block', width: 20 }} />}
                  </td>
                  <td>
                    <input
                      className="ov-debt-input"
                      type="text"
                      placeholder="Account name"
                      value={r.name}
                      onChange={(e) => onSetRow(r._id, 'name', e.target.value)}
                    />
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
                    ><span aria-hidden="true">✕</span></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button type="button" className="ov-btn ov-btn-ghost ov-btn-sm" onClick={onAddRow}>
        + Add debt
      </button>

      <div className="ov-extra-row">
        <label className="ov-extra-label" htmlFor="payoff-extra-input">Extra monthly payment toward debt</label>
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
          disabled={loading || rows.length === 0}
        >
          {loading ? <><Spin /> Calculating…</> : 'Calculate payoff timeline →'}
        </button>
      </div>
    </>
  );
}
