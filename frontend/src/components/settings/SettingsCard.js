import React from 'react';

// Card shell for the settings panes: title, optional right-aligned hint,
// optional head action. `flush` drops body padding for cards whose rows
// own their own (institutions, rules).
export default function SettingsCard({ title, hint, action, flush = false, children }) {
  return (
    <section className="set-card">
      <header className="set-card-head">
        <h3 className="set-card-title">{title}</h3>
        {hint && <span className="set-card-hint">{hint}</span>}
        {action && <div className="set-card-action">{action}</div>}
      </header>
      <div className={flush ? 'set-card-body set-card-body--flush' : 'set-card-body'}>
        {children}
      </div>
    </section>
  );
}
