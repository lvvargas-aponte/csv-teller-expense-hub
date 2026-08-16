import React, { useCallback, useEffect, useState } from 'react';

import Spin from '../ui/Spin';
import Num from './Num';
import KpiCard from '../ui/KpiCard';
import AmortizationTable from './loans/AmortizationTable';
import LoanForm from './loans/LoanForm';
import { fmt$ } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import { createLoan, deleteLoan, listLoans, updateLoan } from '../../api/loans';
import { listProperties } from '../../api/properties';

export default function LoansPage() {
  const [loans, setLoans] = useState([]);
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);   // loan | 'new' | null
  const [saving, setSaving] = useState(false);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([listLoans(), listProperties()])
      .then(([l, p]) => { setLoans(l.data); setProperties(p.data); })
      .catch((e) => setError(userMessage(e, 'Could not load loans.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleSave = async (draft) => {
    setSaving(true);
    setError(null);
    try {
      if (editing && editing !== 'new') await updateLoan(editing.id, draft);
      else await createLoan(draft);
      setEditing(null);
      load();
    } catch (e) {
      setError(userMessage(e, 'Could not save the loan.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (loan) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete ${loan.name}?`)) return;
    try {
      await deleteLoan(loan.id);
      load();
    } catch (e) {
      setError(userMessage(e, 'Could not delete the loan.'));
    }
  };

  const totalDebt = loans.reduce((s, l) => s + (l.current_balance_resolved || 0), 0);
  const totalPayment = loans.reduce((s, l) => s + (l.monthly_payment || 0), 0);
  const totalEquity = loans.reduce((s, l) => s + (l.equity || 0), 0);

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Loans</div>
        <button type="button" className="btn-primary" onClick={() => setEditing('new')}>
          + Add loan
        </button>
      </div>

      <div className="eh-content">
        {error && <div className="ov-error">{error}</div>}

        {loading && loans.length === 0 ? <Spin /> : (
          <>
            <section className="eh-kpi-row">
              <KpiCard label="Total debt" value={fmt$(totalDebt)} barColor="#ef4444"
                       help="Outstanding principal across every loan." />
              <KpiCard label="Monthly payments" value={fmt$(totalPayment)} barColor="#6366f1"
                       help="Principal and interest. Escrow is tracked separately." />
              <KpiCard label="Equity in secured assets" value={fmt$(totalEquity)}
                       barColor="#059669"
                       help="Asset value minus the loan balance, where a value is on file." />
              <KpiCard label="Loans" value={String(loans.length)} barColor="#8b5cf6" />
            </section>

            {loans.length === 0 ? (
              <div className="prop-empty">
                <div className="prop-empty-icon" aria-hidden="true">🏛️</div>
                <div className="prop-empty-title">No loans yet</div>
                <div className="prop-empty-sub">
                  Add a mortgage or auto loan to see how each payment splits
                  between interest and principal.
                </div>
                <button type="button" className="btn-primary" onClick={() => setEditing('new')}>
                  Add your first loan
                </button>
              </div>
            ) : (
              <div className="loan-list">
                {loans.map((loan) => {
                  const property = properties.find(
                    (p) => p.property_id === loan.property_id
                  );
                  const isOpen = openId === loan.id;
                  return (
                    <section key={loan.id} className="loan-row">
                      <div className="loan-row-head">
                        <button
                          type="button"
                          className="loan-row-toggle"
                          onClick={() => setOpenId(isOpen ? null : loan.id)}
                          aria-expanded={isOpen}
                        >
                          <span className="loan-row-caret">{isOpen ? '▾' : '▸'}</span>
                          <span className="loan-row-name">{loan.name}</span>
                          <span className="loan-row-sub">
                            {property ? property.name : loan.loan_type}
                            {' · '}{loan.interest_rate_pct}%
                          </span>
                        </button>
                        <div className="loan-row-figures">
                          <span><Num value={loan.current_balance_resolved} /> owed</span>
                          <span>{fmt$(loan.monthly_payment)}/mo</span>
                          {loan.ltv !== null && loan.ltv !== undefined && (
                            <span>{loan.ltv}% LTV</span>
                          )}
                        </div>
                        <div className="loan-row-actions">
                          <button type="button" onClick={() => setEditing(loan)}>Edit</button>
                          <button type="button" className="btn-danger"
                                  onClick={() => handleDelete(loan)}>Delete</button>
                        </div>
                      </div>
                      {isOpen && <AmortizationTable loan={loan} />}
                    </section>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {editing && (
        <LoanForm
          initial={editing === 'new' ? null : editing}
          properties={properties}
          onSubmit={handleSave}
          onClose={() => setEditing(null)}
          saving={saving}
        />
      )}
    </>
  );
}
