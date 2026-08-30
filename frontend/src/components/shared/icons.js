import React from 'react';

const base = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
};

export function CheckIcon({ size = 13 }) {
  return (
    <svg {...base} width={size} height={size} strokeWidth="2.4">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function AlertIcon({ size = 15 }) {
  return (
    <svg {...base} width={size} height={size} strokeWidth="2">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

export function FlagIcon({ size = 10 }) {
  return (
    <svg {...base} width={size} height={size} strokeWidth="2.4">
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1Z" />
      <line x1="4" y1="22" x2="4" y2="15" />
    </svg>
  );
}

export function SyncIcon({ size = 13 }) {
  return (
    <svg {...base} width={size} height={size} strokeWidth="2">
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}
