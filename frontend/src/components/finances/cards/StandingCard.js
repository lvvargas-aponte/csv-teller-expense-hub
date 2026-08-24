import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getRatios } from '../../../api/health';
import { fmt$ } from '../../../utils/formatting';

// Where the household stands, as an advisor would open: how long the cash
// lasts, how much of income it keeps, and how much of it is already promised
// to lenders. A ratio with no input says what is missing instead of showing a
// confident zero.

const BANDS = {
  savings: { good: 20, warn: 10 },      // ≥20% strong, <10% thin
  dti:     { good: 15, warn: 43 },      // ≤15% comfortable, ≥43% lending ceiling
};

const GOOD = '#059669';
const WARN = '#f59e0b';
const BAD = '#ef4444';

function savingsColor(pct) {
  if (pct === null || pct === undefined) return 'var(--text-muted)';
  if (pct >= BANDS.savings.good) return GOOD;
  if (pct >= BANDS.savings.warn) return WARN;
  return BAD;
}

function dtiColor(pct) {
  if (pct === null || pct === undefined) return 'var(--text-muted)';
  if (pct <= BANDS.dti.good) return GOOD;
  if (pct < BANDS.dti.warn) return WARN;
  return BAD;
}

function runwayColor(covered, target) {
  if (covered === null || covered === undefined) return 'var(--text-muted)';
  if (covered >= target) return GOOD;
  if (covered >= target / 2) return WARN;
  return BAD;
}

function Stat({ label, value, color, reading, action, onAction }) {
  return (
    <div className="eh-standing-stat" role="group" aria-label={label}>
      <div className="eh-standing-stat-label">{label}</div>
      <div className="eh-standing-stat-value" style={{ color }}>{value}</div>
      <div className="eh-standing-stat-reading">{reading}</div>
      {action && (
        <button type="button" className="eh-standing-stat-action" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

export default function StandingCard({ onOpenSettings }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getRatios()
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load your standing.'));
  }, []);

  const loading = data === null && !error;
  const openProfile = () => onOpenSettings?.('profile');

  const fund = data?.emergency_fund;
  const income = data?.income;
  const needsIncome = !income?.monthly;

  const runway = (() => {
    if (!fund) return null;
    if (fund.months_covered === null || fund.months_covered === undefined) {
      return {
        value: '—',
        reading: 'No complete month of spending yet — import or sync a full month.',
      };
    }
    const short = Math.max(0, fund.target_months - fund.months_covered);
    return {
      value: `${fund.months_covered} months`,
      color: runwayColor(fund.months_covered, fund.target_months),
      reading: short > 0
        ? `${short.toFixed(1)} short of your ${fund.target_months}-month target (${fmt$(fund.gap)})`
        : `Covers your ${fund.target_months}-month target — ${fmt$(fund.cash)} in cash`,
    };
  })();

  const savings = (() => {
    if (needsIncome) {
      return {
        value: '—',
        reading: 'Add your monthly income to see how much of it you keep.',
        action: 'Add your income',
      };
    }
    if (data.savings_rate_pct === null || data.savings_rate_pct === undefined) {
      return {
        value: '—',
        reading: 'No complete month of spending yet to measure against.',
      };
    }
    const kept = income.monthly - data.monthly_expenses;
    const basis = income.source === 'detected'
      ? `detected income of ${fmt$(income.monthly)}`
      : `${fmt$(income.monthly)} income`;
    return {
      value: `${data.savings_rate_pct}%`,
      color: savingsColor(data.savings_rate_pct),
      reading: `${fmt$(kept)}/mo kept of ${basis}`,
    };
  })();

  const dti = (() => {
    if (needsIncome) {
      return {
        value: '—',
        reading: 'Add your monthly income to see what share of it is already spoken for.',
        action: 'Add your income',
      };
    }
    return {
      value: `${data.dti_pct}%`,
      color: dtiColor(data.dti_pct),
      reading: `${fmt$(data.monthly_debt_payments)}/mo in minimum payments`,
    };
  })();

  return (
    <DashboardCard
      title="Where you stand"
      loading={loading}
      error={error}
    >
      <div className="eh-standing-grid">
        {runway && (
          <Stat
            label="Emergency runway"
            value={runway.value}
            color={runway.color}
            reading={runway.reading}
          />
        )}
        {savings && (
          <Stat
            label="Savings rate"
            value={savings.value}
            color={savings.color}
            reading={savings.reading}
            action={savings.action}
            onAction={openProfile}
          />
        )}
        {dti && (
          <Stat
            label="Debt-to-income"
            value={dti.value}
            color={dti.color}
            reading={dti.reading}
            action={dti.action}
            onAction={openProfile}
          />
        )}
      </div>
      {income?.source === 'profile'
        && income.detected_monthly
        && Math.abs(income.detected_monthly - income.monthly) >= 1 && (
        <div className="eh-standing-note">
          Using the {fmt$(income.monthly)} you entered — we detect {fmt$(income.detected_monthly)}
          {' '}from your deposits.
        </div>
      )}
    </DashboardCard>
  );
}
