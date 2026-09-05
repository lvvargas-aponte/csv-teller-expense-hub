import React from 'react';

// Stroke-based, 20x20 grid, one visual style. Colour comes from
// currentColor so active/hover/disabled states work — which emoji could
// never do.
const PATHS = {
  home: <><path d="M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z" /></>,
  transactions: <><rect x="3" y="3.5" width="14" height="13" rx="2" /><path d="M6.5 8h7M6.5 11.5h4.5" /></>,
  accounts: <><path d="M3 7.5 10 4l7 3.5" /><path d="M4.5 8.5v6M8.5 8.5v6M11.5 8.5v6M15.5 8.5v6" /><path d="M3 16.5h14" /></>,
  // A card, not the clock face this used to be — the section is cards and
  // loans, and a clock reads as "time".
  debt: <><rect x="2.6" y="5" width="14.8" height="10" rx="2" /><path d="M2.6 8.6h14.8" /><path d="M5.6 12.2h3.4" /></>,
  invest: <><path d="M3.5 13.5 8 9l3 3 5.5-6" /><path d="M12.5 6h4v4" /></>,
  // A checklist on a clipboard. The old bullseye read as a target, which is
  // what `goal` two rows down actually means.
  plan: <><path d="M7.4 3.8H5.5a1.5 1.5 0 0 0-1.5 1.5v10.4a1.5 1.5 0 0 0 1.5 1.5h9a1.5 1.5 0 0 0 1.5-1.5V5.3a1.5 1.5 0 0 0-1.5-1.5h-1.9" /><rect x="7.4" y="2.4" width="5.2" height="2.8" rx="1" /><path d="M7 11.2l1.7 1.7 3.6-3.9" /></>,
  calendar: <><rect x="3" y="4.5" width="14" height="12.5" rx="2" /><path d="M3 8.5h14M7 3v3M13 3v3" /></>,
  goal: <><path d="M5 17V3.6" /><path d="M5 4.2h9.6l-2 3 2 3H5z" /></>,
  // The brand mark, and only that — it sits on the gradient tile in the
  // sidebar. Kept separate from the nav glyphs so redrawing one of those
  // can never silently redraw the logo.
  logo: <><path d="M10 3v14" /><path d="M13.4 6.1c-.7-.9-1.9-1.5-3.4-1.5-2 0-3.4 1-3.4 2.6 0 1.7 1.4 2.3 3.4 2.8 2 .5 3.6 1.1 3.6 2.9 0 1.7-1.5 2.7-3.6 2.7-1.7 0-3-.6-3.7-1.6" /></>,
  // A speech bubble asking something — not the bare circled "?" of `help`
  // below, which sits a few pixels away in the same sidebar.
  ask: <><path d="M4.6 3.5h10.8a2 2 0 0 1 2 2v6.4a2 2 0 0 1-2 2H9.2l-3.6 3v-3H4.6a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2z" /><path d="M8.5 7.4a1.6 1.6 0 1 1 2.05 1.55c-.4.13-.55.42-.55.8v.25" /><path d="M10 11.3v.4" /></>,
  // Eight-tooth cog. The old glyph was a circle with eight radiating ticks,
  // which is the same drawing as `sun` below — two nav items apart.
  settings: <><path d="M8.43 4.73L8.79 2.70L11.21 2.70L11.57 4.73L12.61 5.16L14.30 3.98L16.02 5.70L14.84 7.39L15.27 8.43L17.30 8.79L17.30 11.21L15.27 11.57L14.84 12.61L16.02 14.30L14.30 16.02L12.61 14.84L11.57 15.27L11.21 17.30L8.79 17.30L8.43 15.27L7.39 14.84L5.70 16.02L3.98 14.30L5.16 12.61L4.73 11.57L2.70 11.21L2.70 8.79L4.73 8.43L5.16 7.39L3.98 5.70L5.70 3.98L7.39 5.16Z" /><circle cx="10" cy="10" r="2.5" /></>,
  tag: <><path d="M10.4 3.2H16a1 1 0 0 1 1 1v5.6a1 1 0 0 1-.3.7l-6.4 6.4a1 1 0 0 1-1.4 0l-5.9-5.9a1 1 0 0 1 0-1.4l6.4-6.4a1 1 0 0 1 .7-.3z" /><circle cx="13.4" cy="6.6" r="1.1" /></>,
  shared: <><circle cx="7" cy="8" r="2.6" /><path d="M2.8 16c0-2.3 1.9-4 4.2-4s4.2 1.7 4.2 4" /><path d="M13 5.6a2.6 2.6 0 0 1 0 4.8" /><path d="M14.4 12.4c1.7.5 2.8 1.9 2.8 3.6" /></>,
  history: <><path d="M3.4 10a6.6 6.6 0 1 0 1.9-4.6" /><path d="M3.2 4.2v3.2h3.2" /><path d="M10 6.6V10l2.6 1.6" /></>,
  chevron: <><path d="M7.5 5l5 5-5 5" /></>,
  chevronDown: <><path d="M5 7.5l5 5 5-5" /></>,
  close: <><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" /></>,
  edit: <><path d="M12.6 3.4a1.7 1.7 0 0 1 2.4 2.4l-8.6 8.6-3.2.8.8-3.2z" /><path d="M11.2 4.8l2.4 2.4" /></>,
  plus: <><path d="M10 4.5v11M4.5 10h11" /></>,
  search: <><circle cx="8.8" cy="8.8" r="5" /><path d="M12.5 12.5 16.5 16.5" /></>,
  refresh: <><path d="M16.4 8.4a6.6 6.6 0 1 0-.6 4.4" /><path d="M16.8 4.4v4h-4" /></>,
  warning: <><path d="M10 3.8 17 16H3z" /><path d="M10 8.4v3.2M10 13.6v.6" /></>,
  info: <><circle cx="10" cy="10" r="6.8" /><path d="M10 9.2v4M10 6.9v.5" /></>,
  help: <><circle cx="10" cy="10" r="6.8" /><path d="M8.1 8.05a1.95 1.95 0 1 1 2.55 1.85c-.45.16-.65.5-.65.95v.45" /><path d="M10 13.7v.5" /></>,
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
