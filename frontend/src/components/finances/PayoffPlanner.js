import React from 'react';
import Spin from '../ui/Spin';
import { usePayoffPlanner } from './payoff/usePayoffPlanner';
import PayoffForm from './payoff/PayoffForm';
import PayoffResults from './payoff/PayoffResults';
import PayoffAdvice from './payoff/PayoffAdvice';

export default function PayoffPlanner({ creditAccounts = [] }) {
  const planner = usePayoffPlanner(creditAccounts);

  return (
    <div className="ov-card">
      <div className="ov-card-header">
        <div>
          <div className="ov-card-title">Debt Payoff Planner</div>
          <div className="ov-card-subtitle">Enter APR and minimum payments to see your payoff timeline</div>
        </div>
        <button
          type="button"
          className="ov-btn ov-btn-secondary ov-btn-sm"
          onClick={planner.handleGetAdvice}
          disabled={planner.adviceLoading || planner.rows.length === 0}
          title="Ask Fin for personalised advice on this plan"
        >
          {planner.adviceLoading ? <><Spin /> Thinking…</> : '🤖 Ask Fin'}
        </button>
      </div>

      <div className="ov-card-body">
        <PayoffForm
          rows={planner.rows}
          strategy={planner.strategy}
          extra={planner.extra}
          error={planner.error}
          loading={planner.loading}
          orderById={planner.orderById}
          onSetRow={planner.setRow}
          onPersistApr={planner.persistApr}
          onPersistDetail={planner.persistDetail}
          onAddRow={planner.addRow}
          onRemoveRow={planner.removeRow}
          onStrategyChange={planner.handleStrategyChange}
          onExtraChange={planner.setExtraPayment}
          onCalculate={planner.handleCalculate}
        />

        <PayoffResults
          results={planner.results}
          strategy={planner.strategy}
          totalMonths={planner.totalMonths}
          totalPaid={planner.totalPaid}
          rows={planner.rows}
        />

        <PayoffAdvice advice={planner.advice} adviceError={planner.adviceError} />
      </div>
    </div>
  );
}
