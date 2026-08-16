import React, { useCallback, useEffect, useState } from 'react';
import {
  Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend,
} from 'recharts';

import Spin from '../../ui/Spin';
import Num from '../Num';
import { fmt$, fmtDate } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { getCurrentPayment, getSchedule, getWhatIf } from '../../../api/loans';

const PAGE = 60;

export default function AmortizationTable({ loan }) {
  const [schedule, setSchedule] = useState(null);
  const [current, setCurrent] = useState(null);
  const [whatIf, setWhatIf] = useState(null);
  const [extra, setExtra] = useState('200');
  const [fromPeriod, setFromPeriod] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getSchedule(loan.id, { fromPeriod, limit: PAGE }),
      getCurrentPayment(loan.id),
    ])
      .then(([s, c]) => { setSchedule(s.data); setCurrent(c.data); })
      .catch((e) => setError(userMessage(e, 'Could not load the schedule.')))
      .finally(() => setLoading(false));
  }, [loan.id, fromPeriod]);

  useEffect(load, [load]);

  const runWhatIf = async () => {
    try {
      const r = await getWhatIf(loan.id, parseFloat(extra) || 0);
      setWhatIf(r.data);
    } catch (e) {
      setError(userMessage(e, 'Could not run the comparison.'));
    }
  };

  if (loading && !schedule) return <section className="ov-card"><Spin /></section>;
  if (error) return <section className="ov-card"><div className="ov-error">{error}</div></section>;
  if (!schedule) return null;

  // Chart the split rather than the balance: watching interest give way to
  // principal is the thing that makes amortization legible.
  const chartData = schedule.periods.map((p) => ({
    period: p.period,
    Principal: p.principal + p.extra,
    Interest: p.interest,
  }));

  const totalPeriods = schedule.total_periods || 0;
  const canPrev = fromPeriod > 1;
  const canNext = fromPeriod + PAGE <= totalPeriods;

  return (
    <section className="ov-card amort">
      <div className="ov-card-header">
        <div className="ov-card-title">{loan.name}</div>
        <div className="ov-card-subtitle">
          {fmt$(schedule.monthly_payment)}/mo principal &amp; interest
          {schedule.escrow_monthly > 0 && <> · {fmt$(schedule.escrow_monthly)} escrow</>}
          {schedule.payoff_date && <> · paid off {fmtDate(schedule.payoff_date)}</>}
        </div>
      </div>

      <div className="ov-card-body">
        {schedule.negative_amortization && (
          <div className="amort-warning">
            This payment doesn&apos;t cover the monthly interest, so the balance
            grows rather than shrinking. The loan never pays off at this rate.
          </div>
        )}

        {current && current.period > 0 && (
          <div className="amort-current">
            <div className="amort-current-title">
              Payment #{current.period} — this month
            </div>
            <div className="amort-current-split">
              <div className="amort-split-item">
                <span className="amort-split-label">Interest</span>
                <span className="amort-split-value neg"><Num value={current.interest} /></span>
              </div>
              <div className="amort-split-item">
                <span className="amort-split-label">Principal</span>
                <span className="amort-split-value pos"><Num value={current.principal} /></span>
              </div>
              {current.escrow > 0 && (
                <div className="amort-split-item">
                  <span className="amort-split-label">Escrow</span>
                  <span className="amort-split-value"><Num value={current.escrow} /></span>
                </div>
              )}
              <div className="amort-split-item">
                <span className="amort-split-label">Balance</span>
                <span className="amort-split-value"><Num value={current.balance} /></span>
              </div>
            </div>
            <div className="amort-current-note">
              <Num value={current.cumulative_principal_paid} /> of principal paid down so far.
            </div>
          </div>
        )}

        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11 }} width={56}
                   tickFormatter={(v) => `$${Math.round(v)}`} />
            <Tooltip
              formatter={(value, name) => [fmt$(value), name]}
              labelFormatter={(l) => `Payment #${l}`}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="Interest" stackId="p" fill="#ef4444" />
            <Bar dataKey="Principal" stackId="p" fill="#059669" />
          </BarChart>
        </ResponsiveContainer>

        <div className="amort-whatif">
          <label htmlFor={`extra-${loan.id}`}>Pay extra each month</label>
          <input
            id={`extra-${loan.id}`}
            type="number"
            step="any"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
          />
          <button type="button" onClick={runWhatIf}>See the difference</button>
          {whatIf && (
            <span className="amort-whatif-result">
              {whatIf.months_saved} months sooner, {fmt$(whatIf.interest_saved)} saved
            </span>
          )}
        </div>

        <div className="amort-table-wrap">
          <table className="amort-table">
            <thead>
              <tr>
                <th>#</th><th>Date</th><th>Payment</th>
                <th>Principal</th><th>Interest</th><th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {schedule.periods.map((p) => (
                <tr key={p.period}>
                  <td>{p.period}</td>
                  <td>{fmtDate(p.date)}</td>
                  <td>{fmt$(p.payment)}</td>
                  <td className="pos">{fmt$(p.principal + p.extra)}</td>
                  <td className="neg">{fmt$(p.interest)}</td>
                  <td>{fmt$(p.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="amort-pager">
          <button type="button" disabled={!canPrev}
                  onClick={() => setFromPeriod((p) => Math.max(1, p - PAGE))}>
            ‹ Earlier
          </button>
          <span>
            Payments {fromPeriod}–{Math.min(fromPeriod + PAGE - 1, totalPeriods)} of {totalPeriods}
          </span>
          <button type="button" disabled={!canNext}
                  onClick={() => setFromPeriod((p) => p + PAGE)}>
            Later ›
          </button>
        </div>

        <div className="amort-totals">
          Total interest over the life of the loan: <Num value={schedule.total_interest} />
        </div>
      </div>
    </section>
  );
}
