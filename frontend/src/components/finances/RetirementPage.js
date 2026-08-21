import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../ui/Spin';
import Num from './Num';
import ProjectionChart from './retirement/ProjectionChart';
import AssumptionsForm from './retirement/AssumptionsForm';
import GoalCard from './retirement/GoalCard';
import { fmt$ } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import {
  getAssumptions, getProjection, runWhatIf, saveAssumptions,
} from '../../api/retirement';

function Hero({ projection }) {
  if (projection.feasible) {
    return (
      <section className="ret-hero">
        <div className="ret-hero-label">On these assumptions, you could retire in</div>
        <div className="ret-hero-value">{projection.earliest_retirement_year}</div>
        <div className="ret-hero-sub">
          at age {projection.earliest_retirement_age} —
          {' '}{projection.years_away} year{projection.years_away === 1 ? '' : 's'} from now
        </div>
      </section>
    );
  }

  const required = projection.required_monthly_contribution;
  return (
    <section className="ret-hero ret-hero--short">
      <div className="ret-hero-label">Not yet reachable</div>
      <div className="ret-hero-value">
        {required ? `${fmt$(required)}/mo` : '—'}
      </div>
      <div className="ret-hero-sub">
        {required
          ? 'investing this much each month would close the gap'
          : "no contribution closes the gap inside the horizon — the spending target may need to come down"}
      </div>
    </section>
  );
}

function AtRetirement({ at }) {
  if (!at) return null;
  const rows = [
    ['Rental profit', at.rental_net, 'After expenses, debt service and tax.'],
    ['Investment withdrawals', at.withdrawal_capacity, 'At your safe withdrawal rate, after tax.'],
    ['Social Security', at.social_security, ''],
  ].filter(([, v]) => v > 0);

  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">Where the money comes from</div>
        <div className="ov-card-subtitle">In {at.year}, at age {at.age}</div>
      </div>
      <div className="ov-card-body">
        {rows.map(([label, value, hint]) => (
          <div className="prop-row" key={label}>
            <span className="prop-row-label" title={hint}>{label}</span>
            <span className="prop-row-value"><Num value={value} />/yr</span>
          </div>
        ))}
        <div className="prop-row prop-row--emphasis">
          <span className="prop-row-label">Total income</span>
          <span className="prop-row-value"><Num value={at.total_income} />/yr</span>
        </div>
        <div className="prop-row">
          <span className="prop-row-label">What you need</span>
          <span className="prop-row-value"><Num value={at.spending_need} />/yr</span>
        </div>
        <div className="prop-row prop-row--emphasis">
          <span className="prop-row-label">Surplus</span>
          <span className={`prop-row-value ${at.surplus < 0 ? 'neg' : 'pos'}`}>
            <Num value={at.surplus} />/yr
          </span>
        </div>
      </div>
    </section>
  );
}

function Milestones({ milestones }) {
  if (!milestones?.length) return null;
  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">When the mortgages finish</div>
        <div className="ov-card-subtitle">
          Each payoff permanently raises that property&apos;s income —
          the tenants bought it, and the payment stops
        </div>
      </div>
      <div className="ov-card-body">
        {milestones.map((m) => (
          <div className="prop-row" key={`${m.year}-${m.mortgages_retired.join()}`}>
            <span className="prop-row-label">
              {m.year} · age {m.age}
            </span>
            <span className="prop-row-value ret-milestone">
              {m.mortgages_retired.join(', ')}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Sensitivity({ rows, baseline }) {
  if (!rows?.length) return null;
  return (
    <section className="ov-card">
      <div className="ov-card-header">
        <div className="ov-card-title">If an assumption is wrong</div>
        <div className="ov-card-subtitle">
          This is a deterministic projection, not a probability. These rows
          say how much the answer moves when one input changes.
        </div>
      </div>
      <div className="ov-card-body">
        {rows.map((s) => {
          const slip = s.earliest_retirement_year && baseline
            ? s.earliest_retirement_year - baseline
            : null;
          return (
            <div className="prop-row" key={s.label}>
              <span className="prop-row-label">{s.label}</span>
              <span className="prop-row-value">
                {s.feasible ? s.earliest_retirement_year : 'out of reach'}
                {slip > 0 && <span className="ret-slip"> +{slip}y</span>}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function RetirementPage() {
  const [projection, setProjection] = useState(null);
  const [assumptions, setAssumptions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([getProjection(), getAssumptions()])
      .then(([p, a]) => {
        setProjection(p.data);
        setAssumptions(a.data.assumptions);
        setPreview(false);
      })
      .catch((e) => setError(userMessage(e, 'Could not load the projection.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleSave = async (payload) => {
    setSaving(true);
    setError(null);
    try {
      await saveAssumptions(payload);
      load();
    } catch (e) {
      setError(userMessage(e, 'Could not save those assumptions.'));
    } finally {
      setSaving(false);
    }
  };

  const handleWhatIf = async (payload) => {
    setError(null);
    try {
      const r = await runWhatIf(payload);
      setProjection(r.data);
      setPreview(true);
    } catch (e) {
      setError(userMessage(e, 'Could not run that scenario.'));
    }
  };

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Retirement</div>
      </div>

      <div className="eh-content">
        {error && <div className="ov-error">{error}</div>}

        {loading && !projection ? <Spin /> : projection && (
          <>
            {preview && (
              <div className="ret-preview">
                Previewing unsaved assumptions.
                <button type="button" onClick={load}>Back to saved</button>
              </div>
            )}

            <Hero projection={projection} />

            {projection.warnings?.length > 0 && (
              <section className="prop-alert">
                <ul>
                  {projection.warnings.map((w) => <li key={w}>{w}</li>)}
                </ul>
              </section>
            )}

            <GoalCard goal={projection.goal} />

            <section className="ov-card">
              <div className="ov-card-header">
                <div className="ov-card-title">Income against what you need</div>
                <div className="ov-card-subtitle">
                  Rental profit rises as mortgages finish; spending rises with
                  inflation. Retirement is where the shaded area clears the line
                  — and stays clear.
                </div>
              </div>
              <div className="ov-card-body">
                <ProjectionChart
                  rows={projection.rows}
                  retirementYear={projection.earliest_retirement_year}
                />
              </div>
            </section>

            <AtRetirement at={projection.at_retirement} />
            <Milestones milestones={projection.milestones} />
            <Sensitivity
              rows={projection.sensitivity}
              baseline={projection.earliest_retirement_year}
            />

            {assumptions && (
              <AssumptionsForm
                assumptions={assumptions}
                onSave={handleSave}
                onWhatIf={handleWhatIf}
                saving={saving}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
