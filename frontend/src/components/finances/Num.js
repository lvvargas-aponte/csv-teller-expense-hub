import React, { createContext, useContext } from 'react';
import { fmt$, fmtSigned } from '../../utils/formatting';

export const BlurContext = createContext(false);

export default function Num({ value, signed, prefix, suffix }) {
  const blur = useContext(BlurContext);
  const text = signed ? fmtSigned(value) : fmt$(value);
  return (
    <span className={blur ? 'eh-blur' : ''}>
      {prefix}{text}{suffix}
    </span>
  );
}

// Blurs dollar tokens embedded in a free-form string (e.g. server-formatted
// alert messages: "You spent $1,234 on Dining"). The non-money words remain
// readable so the user still sees context.
const MONEY_SPLIT = /(-?\$[\d,]+(?:\.\d+)?)/g;
const MONEY_MATCH = /^-?\$[\d,]+(?:\.\d+)?$/;
export function BlurMoney({ text }) {
  const blur = useContext(BlurContext);
  if (!blur || !text) return text || null;
  const parts = text.split(MONEY_SPLIT);
  return parts.map((p, i) =>
    MONEY_MATCH.test(p)
      ? <span key={i} className="eh-blur">{p}</span>
      : <React.Fragment key={i}>{p}</React.Fragment>
  );
}
