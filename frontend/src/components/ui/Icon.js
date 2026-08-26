import React from 'react';

// Stroke-based, 20x20 grid, one visual style. Colour comes from
// currentColor so active/hover/disabled states work — which emoji could
// never do.
const PATHS = {
  home: <><path d="M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z" /></>,
  transactions: <><rect x="3" y="3.5" width="14" height="13" rx="2" /><path d="M6.5 8h7M6.5 11.5h4.5" /></>,
  accounts: <><path d="M3 7.5 10 4l7 3.5" /><path d="M4.5 8.5v6M8.5 8.5v6M11.5 8.5v6M15.5 8.5v6" /><path d="M3 16.5h14" /></>,
  debt: <><circle cx="10" cy="10" r="6.5" /><path d="M10 3.5v6.5l4.6 2.6" /></>,
  invest: <><path d="M3.5 13.5 8 9l3 3 5.5-6" /><path d="M12.5 6h4v4" /></>,
  plan: <><circle cx="10" cy="10" r="6.5" /><circle cx="10" cy="10" r="2.5" /></>,
  calendar: <><rect x="3" y="4.5" width="14" height="12.5" rx="2" /><path d="M3 8.5h14M7 3v3M13 3v3" /></>,
  goal: <><path d="M5 17V3.6" /><path d="M5 4.2h9.6l-2 3 2 3H5z" /></>,
  ask: <><path d="M10 3.2l1.9 4.2 4.6.5-3.4 3.1.9 4.5-4-2.3-4 2.3.9-4.5L3.5 7.9l4.6-.5z" /></>,
  settings: <><circle cx="10" cy="10" r="2.6" /><path d="M10 2.8v2M10 15.2v2M17.2 10h-2M4.8 10h-2M15.1 4.9l-1.4 1.4M6.3 13.7l-1.4 1.4M15.1 15.1l-1.4-1.4M6.3 6.3 4.9 4.9" /></>,
  tag: <><path d="M10.4 3.2H16a1 1 0 0 1 1 1v5.6a1 1 0 0 1-.3.7l-6.4 6.4a1 1 0 0 1-1.4 0l-5.9-5.9a1 1 0 0 1 0-1.4l6.4-6.4a1 1 0 0 1 .7-.3z" /><circle cx="13.4" cy="6.6" r="1.1" /></>,
  shared: <><circle cx="7" cy="8" r="2.6" /><path d="M2.8 16c0-2.3 1.9-4 4.2-4s4.2 1.7 4.2 4" /><path d="M13 5.6a2.6 2.6 0 0 1 0 4.8" /><path d="M14.4 12.4c1.7.5 2.8 1.9 2.8 3.6" /></>,
  history: <><path d="M3.4 10a6.6 6.6 0 1 0 1.9-4.6" /><path d="M3.2 4.2v3.2h3.2" /><path d="M10 6.6V10l2.6 1.6" /></>,
  chevron: <><path d="M7.5 5l5 5-5 5" /></>,
  chevronDown: <><path d="M5 7.5l5 5 5-5" /></>,
  close: <><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" /></>,
  plus: <><path d="M10 4.5v11M4.5 10h11" /></>,
  search: <><circle cx="8.8" cy="8.8" r="5" /><path d="M12.5 12.5 16.5 16.5" /></>,
  refresh: <><path d="M16.4 8.4a6.6 6.6 0 1 0-.6 4.4" /><path d="M16.8 4.4v4h-4" /></>,
  warning: <><path d="M10 3.8 17 16H3z" /><path d="M10 8.4v3.2M10 13.6v.6" /></>,
  info: <><circle cx="10" cy="10" r="6.8" /><path d="M10 9.2v4M10 6.9v.5" /></>,
  sun: <><circle cx="10" cy="10" r="3.4" /><path d="M10 2.6v1.8M10 15.6v1.8M17.4 10h-1.8M4.4 10H2.6M15.2 4.8l-1.3 1.3M6.1 13.9l-1.3 1.3M15.2 15.2l-1.3-1.3M6.1 6.1 4.8 4.8" /></>,
  moon: <><path d="M16 11.4A6.6 6.6 0 0 1 8.6 4a6.8 6.8 0 1 0 7.4 7.4z" /></>,
};

export const ICON_NAMES = Object.keys(PATHS);

export default function Icon({ name, size = 18, strokeWidth = 1.6, className }) {
  const paths = PATHS[name];
  if (!paths) return null;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths}
    </svg>
  );
}
