import React, { useId } from 'react';

// Pairs a `<label>` with its single input/select child via a generated id.
// Pass `hint` to render small helper text below the control.
export default function Field({ label, hint, children }) {
  const id = useId();
  return (
    <div className="field-group">
      <label className="field-label" htmlFor={id}>{label}</label>
      {React.cloneElement(children, { id })}
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  );
}
