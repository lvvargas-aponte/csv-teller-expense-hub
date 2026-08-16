import React, { useCallback, useEffect, useMemo, useState } from 'react';

import Spin from '../ui/Spin';
import Num, { BlurContext } from './Num';
import SafeToSpendCard from './cards/SafeToSpendCard';
import NextActionsCard from './cards/NextActionsCard';
import { getSafeToSpend } from '../../api/budgets';
import { getUpcomingBills } from '../../api/dashboard';
import { getPortfolio } from '../../api/properties';
import { fmt$, greetingFor, formatToday, toYMD } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';

/** Horizontal flow of where the month's income has been committed. */
function MonthFlow({ data }) {
  if (!data?.available) return null;
  const { income, commitments } = data;
  const total = Math.max(income.monthly, 1);

  const segments = [
    { key: 'Bills', value: commitments.fixed_bills, color: '#f59e0b' },
    { key: 'Debt', value: commitments.minimum_debt_payments, color: '#ef4444' },
    { key: 'Goals', value: commitments.required_goal_contributions, color: '#6366f1' },
    { key: 'Spent', value: data.spent_so_far, color: '#8b5cf6' },
    { key: 'Left', value: Math.max(0, data.remaining_pool), color: '#059669' },
  ].filter((s) => s.value > 0);

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Where this month goes</div>
        <div className="ov-card-subtitle">
          {fmt$(income.monthly)} in, {fmt$(commitments.total)} already promised
        </div>
      </div>
      <div className="ov-card-body">
        <div className="today-flow">
          {segments.map((s) => (
            <div
              key={s.key}
              className="today-flow-seg"
              style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
              title={`${s.key}: ${fmt$(s.value)}`}
            />
          ))}
        </div>
        <div className="today-flow-legend">
          {segments.map((s) => (
            <span key={s.key}>
              <i style={{ background: s.color }} aria-hidden="true" />
              {s.key} <Num value={s.value} />
            </span>
          ))}
        </div>

        {data.excluded_categories.length > 0 && (
          <div className="today-note">
            Recurring bills are counted once as commitments, so they don&apos;t
            also eat into the daily number:
            {' '}{data.excluded_categories.join(', ')}.
          </div>
        )}
        {data.caveats.map((c) => (
          <div key={c} className="today-note today-note--caveat">{c}</div>
        ))}
      </div>
    </section>
  );
}

// A credit card's due figure is its minimum payment; a detected recurring
// charge only carries its average amount in `balance`.
const billAmount = (bill) => bill.minimum_payment ?? bill.balance ?? 0;

function WeekAhead({ bills, remaining }) {
  const soon = useMemo(() => (bills || []).slice(0, 6), [bills]);
  if (soon.length === 0) return null;

  let running = remaining;
  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Coming up</div>
        <div className="ov-card-subtitle">
          Running total shows what&apos;s left after each one clears
        </div>
      </div>
      <div className="ov-card-body">
        <table className="today-bills">
          <tbody>
            {soon.map((bill) => {
              running -= billAmount(bill);
              return (
                <tr key={`${bill.name}-${bill.due_date}`}>
                  <td>{bill.name}</td>
                  <td className="today-bills-date">
                    {bill.days_until === 0 ? 'today'
                      : bill.days_until === 1 ? 'tomorrow'
                      : `in ${bill.days_until} days`}
                  </td>
                  <td className="today-bills-amt"><Num value={billAmount(bill)} /></td>
                  <td className="today-bills-after">
                    leaves <Num value={Math.max(0, running)} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ProgressStrip({ portfolio }) {
  if (!portfolio || portfolio.count === 0) return null;
  return (
    <section className="today-progress">
      <div className="today-progress-item">
        <span className="today-progress-label">Property equity</span>
        <span className="today-progress-value"><Num value={portfolio.total_equity} /></span>
      </div>
      <div className="today-progress-item">
        <span className="today-progress-label">Rental cash flow</span>
        <span className="today-progress-value">
          <Num value={portfolio.monthly_cash_flow} signed />/mo
        </span>
      </div>
      <div className="today-progress-item">
        <span className="today-progress-label">Principal paid down</span>
        <span className="today-progress-value">
          <Num value={portfolio.ytd_principal_paid} />
        </span>
      </div>
    </section>
  );
}

export default function TodayPage({ onNavigate }) {
  const [data, setData] = useState(null);
  const [yesterday, setYesterday] = useState(null);
  const [bills, setBills] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const priorDay = new Date();
    priorDay.setDate(priorDay.getDate() - 1);

    Promise.all([
      getSafeToSpend(),
      // Yesterday's figure, so the change can be attributed rather than
      // just observed.
      getSafeToSpend(toYMD(priorDay)).catch(() => ({ data: null })),
      getUpcomingBills().catch(() => ({ data: { bills: [] } })),
      getPortfolio().catch(() => ({ data: null })),
    ])
      .then(([sts, prior, b, p]) => {
        setData(sts.data);
        setYesterday(prior.data);
        setBills(b.data?.bills || []);
        setPortfolio(p.data);
      })
      .catch((e) => setError(userMessage(e, 'Could not load today.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const today = useMemo(() => new Date(), []);

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Today</div>
      </div>

      <div className="eh-content">
        <div className="today-greeting">
          {greetingFor(today)}, {formatToday(today)}
        </div>

        {error && <div className="ov-error">{error}</div>}
        {loading && !data ? <Spin /> : (
          <BlurContext.Provider value={false}>
            <SafeToSpendCard data={data} yesterday={yesterday} />
            <NextActionsCard onNavigate={onNavigate} />
            <MonthFlow data={data} />
            <WeekAhead bills={bills} remaining={data?.remaining_pool ?? 0} />
            <ProgressStrip portfolio={portfolio} />
          </BlurContext.Provider>
        )}
      </div>
    </>
  );
}
