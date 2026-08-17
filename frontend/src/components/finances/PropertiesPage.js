import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../ui/Spin';
import Num from './Num';
import KpiCard from '../ui/KpiCard';
import PropertyCard from './properties/PropertyCard';
import PropertyDetail from './properties/PropertyDetail';
import PropertyForm from './properties/PropertyForm';
import { fmt$, fmtSigned } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import {
  createProperty, deleteProperty, getPortfolio, updateProperty,
} from '../../api/properties';

export default function PropertiesPage() {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [editing, setEditing] = useState(null);   // property object | 'new' | null
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    getPortfolio()
      .then((r) => setPortfolio(r.data))
      .catch((e) => setError(userMessage(e, 'Could not load properties.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleSave = async (draft) => {
    setSaving(true);
    setError(null);
    try {
      if (editing && editing !== 'new') {
        await updateProperty(editing.property_id, draft);
      } else {
        await createProperty(draft);
      }
      setEditing(null);
      load();
    } catch (e) {
      setError(userMessage(e, 'Could not save the property.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (property) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(
      `Delete ${property.name}?\n\nIts valuations go too. Any loan against it `
      + 'is kept, with the property link cleared.'
    )) return;
    try {
      await deleteProperty(property.property_id);
      setSelectedId(null);
      load();
    } catch (e) {
      setError(userMessage(e, 'Could not delete the property.'));
    }
  };

  const selected = portfolio?.properties?.find((p) => p.property_id === selectedId);

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Properties</div>
        <button type="button" className="btn-primary" onClick={() => setEditing('new')}>
          + Add property
        </button>
      </div>

      <div className="eh-content">
        {error && <div className="ov-error">{error}</div>}

        {loading && !portfolio ? <Spin /> : selected ? (
          <PropertyDetail
            property={selected}
            onBack={() => setSelectedId(null)}
            onEdit={setEditing}
            onDelete={handleDelete}
            onChanged={load}
          />
        ) : (
          <>
            <section className="eh-kpi-row">
              <KpiCard
                label="Portfolio value"
                value={fmt$(portfolio?.total_value)}
                sub={portfolio?.total_debt ? `${fmt$(portfolio.total_debt)} debt` : null}
                barColor="#059669"
                help="Sum of the latest recorded value for every property."
              />
              <KpiCard
                label="Equity"
                value={fmt$(portfolio?.total_equity)}
                sub={portfolio?.portfolio_ltv === null || portfolio?.portfolio_ltv === undefined
                  ? null : `${portfolio.portfolio_ltv.toFixed(2)}% LTV`}
                barColor="#059669"
                help="Value minus outstanding loan balances — what you'd keep after paying off the debt."
              />
              <KpiCard
                label="Monthly cash flow"
                value={fmtSigned(portfolio?.monthly_cash_flow)}
                valueClass={(portfolio?.monthly_cash_flow ?? 0) < 0
                  ? 'eh-kpi-value--neg' : 'eh-kpi-value--pos'}
                barColor={(portfolio?.monthly_cash_flow ?? 0) < 0 ? '#ef4444' : '#059669'}
                help="Net operating income minus debt service across every property."
              />
              <KpiCard
                label="Principal paid down"
                value={fmt$(portfolio?.ytd_principal_paid)}
                barColor="#6366f1"
                help="How much of your mortgages the rent has retired so far."
              />
            </section>

            {portfolio?.underperforming?.length > 0 && (
              <section className="prop-alert">
                <div className="prop-alert-title">
                  {portfolio.underperforming.length} propert
                  {portfolio.underperforming.length === 1 ? 'y needs' : 'ies need'} a look
                </div>
                <ul>
                  {portfolio.underperforming.map((p) => (
                    <li key={p.property_id}>
                      <strong>{p.name}</strong> — {p.reasons[0]}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {portfolio?.count === 0 ? (
              <div className="prop-empty">
                <div className="prop-empty-icon" aria-hidden="true">🏠</div>
                <div className="prop-empty-title">No properties yet</div>
                <div className="prop-empty-sub">
                  Add one to track equity, rental cash flow, and how much of the
                  mortgage your tenants have paid off.
                </div>
                <button type="button" className="btn-primary" onClick={() => setEditing('new')}>
                  Add your first property
                </button>
              </div>
            ) : (
              <div className="prop-grid">
                {portfolio?.properties?.map((property) => (
                  <PropertyCard
                    key={property.property_id}
                    property={property}
                    onOpen={setSelectedId}
                  />
                ))}
              </div>
            )}

            {portfolio?.count > 0 && (
              <div className="prop-footnote">
                Portfolio LTV {portfolio.portfolio_ltv ?? '—'}% ·
                {' '}<Num value={portfolio.total_debt} /> of debt against
                {' '}<Num value={portfolio.total_value} /> of value
              </div>
            )}
          </>
        )}
      </div>

      {editing && (
        <PropertyForm
          initial={editing === 'new' ? null : editing}
          onSubmit={handleSave}
          onClose={() => setEditing(null)}
          saving={saving}
        />
      )}
    </>
  );
}
