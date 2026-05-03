import React, { useRef } from 'react';
import { Z_BACKDROP_DEFAULT } from '../../utils/zIndex';

export default function Backdrop({ onClose, children, zIndex = Z_BACKDROP_DEFAULT }) {
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
