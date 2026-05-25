import React from 'react';

export default function PayoffAdvice({ advice, adviceError }) {
  return (
    <>
      {adviceError && (
        <div className="ov-ai-card ov-ai-card--nudge">
          <div className="ov-ai-card-label">AI advisor unavailable</div>
          <div style={{ fontSize: 13 }}>{adviceError}</div>
        </div>
      )}
      {advice && (
        <div className="ov-ai-card">
          <div className="ov-ai-card-label">AI advisor</div>
          <div className="ov-ai-card-body">{advice}</div>
        </div>
      )}
    </>
  );
}
