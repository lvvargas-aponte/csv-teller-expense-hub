import React, { useRef } from 'react';

export default function Backdrop({ onClose, children, zIndex = 200 }) {
  const ref = useRef(null);
  return (
    <div
      ref={ref}
      className="backdrop"
      style={{ zIndex }}
      onMouseDown={(e) => { if (e.target === ref.current) onClose(); }}
    >
      {children}
    </div>
  );
}
