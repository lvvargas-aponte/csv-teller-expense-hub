import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../ui/Spin';
import Num from './Num';
import WaterfallList from './allocate/WaterfallList';
import AllocationSettingsForm from './allocate/AllocationSettingsForm';
import { userMessage } from '../../utils/errorMessage';
import {
  allocate, getAllocationSettings, saveAllocationSettings,
} from '../../api/tools';

const PRESETS = [100, 250, 500, 1000];

export default function AllocatePage() {
  const [amount, setAmount] = useState('500');
  const [cadence, setCadence] = useState('monthly');
  const [plan, setPlan] = useState(null);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback((value, mode) => {
    const parsed = parseFloat(value);
    if (!parsed || parsed <= 0) {
      setPlan(null);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return allocate({ amount: parsed, cadence: mode })
      .then((r) => setPlan(r.data))
      .catch((e) => setError(userMessage(e, 'Could not work out a split.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getAllocationSettings()
      .then((r) => setSettings(r.data))
      .catch(() => { /* the waterfall still runs on defaults */ });
  }, []);

  useEffect(() => { run(amount, cadence); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSaveSettings = async (payload) => {
    setSaving(true);
    try {
      const r = await saveAllocationSettings(payload);
      setSettings(r.data);
      await run(amount, cadence);
    } catch (e) {
      setError(userMessage(e, 'Could not save those settings.'));
    } finally {
      setSaving(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    run(amount, cadence);
  };

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Spare money</div>
      </div>

      <div className="eh-content">
        {error && <div className="ov-error">{error}</div>}

        <form className="ov-card alloc-input" onSubmit={submit}>
          <div className="ov-card-header">
            <div className="ov-card-title">How much have you got spare?</div>
            <div className="ov-card-subtitle">
              The answer runs in a fixed order — match, buffer, expensive debt,
              tax-advantaged, property, then the market. The ordering isn&apos;t
              taste; a 50% employer match beats a 24% card beats a 3% mortgage.
            </div>
          </div>

          <div className="ov-card-body">
            <div className="alloc-controls">
              <label className="alloc-amount">
                <span className="prop-field-label">Amount</span>
                <input
                  type="number"
                  step="any"
                  min="1"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </label>

              <label className="alloc-cadence">
                <span className="prop-field-label">This is</span>
                <select value={cadence} onChange={(e) => setCadence(e.target.value)}>
                  <option value="monthly">every month</option>
                  <option value="one_time">a one-off (bonus, refund)</option>
                </select>
              </label>

              <button type="submit" className="btn-primary">Work it out</button>
            </div>

            <div className="alloc-presets">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="alloc-preset"
                  onClick={() => { setAmount(String(p)); run(p, cadence); }}
                >
                  ${p.toLocaleString()}
                </button>
              ))}
            </div>
          </div>
        </form>

        {loading && !plan ? <Spin /> : plan && plan.available && (
          <>
            <section className="alloc-hero">
              <div className="alloc-hero-label">
                {plan.cadence === 'monthly' ? 'Every month' : 'One-off'}
              </div>
              <div className="alloc-hero-value"><Num value={plan.amount} /></div>
              <div className="alloc-hero-sub">
                split across {plan.allocations.length} place
                {plan.allocations.length === 1 ? '' : 's'}
                {plan.unallocated > 0 && (
                  <> · <Num value={plan.unallocated} /> unallocated</>
                )}
              </div>
            </section>

            <WaterfallList plan={plan} />
          </>
        )}

        {settings && (
          <AllocationSettingsForm
            settings={settings}
            onSave={handleSaveSettings}
            saving={saving}
          />
        )}
      </div>
    </>
  );
}
