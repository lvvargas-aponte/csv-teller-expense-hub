import React from 'react';
import { render, screen } from '@testing-library/react';
import SpendingByCategoryCard from '../SpendingByCategoryCard';

// jsdom has no ResizeObserver, so recharts' <ResponsiveContainer> never
// measures its box and never renders series — a no-op-callback polyfill
// plus a fixed getBoundingClientRect is what lets the chart lay out enough
// for its <Legend> (which mirrors each <Bar>'s `fill`) to render.
class ResizeObserverStub {
  constructor(cb) { this.cb = cb; }

  observe(el) { this.cb([{ target: el, contentRect: el.getBoundingClientRect() }]); }

  unobserve() {}

  disconnect() {}
}

let originalGetBoundingClientRect;
beforeAll(() => {
  global.ResizeObserver = ResizeObserverStub;
  originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = () => ({
    width: 800, height: 240, top: 0, left: 0, bottom: 240, right: 800, x: 0, y: 0, toJSON() {},
  });
});

afterAll(() => {
  delete global.ResizeObserver;
  Element.prototype.getBoundingClientRect = originalGetBoundingClientRect;
});

// Nine categories in one month: eight named plus a ninth that falls past
// TOP_N=8 into "Other" — the exact shape that collided when the palette
// was six colours cycling with `i % PALETTE.length`.
const dashboard = {
  months: ['Jun'],
  spending_by_month: {
    Jun: {
      Rent: 1500, Groceries: 500, Dining: 200, Utilities: 150,
      Shopping: 300, Transport: 100, Entertainment: 80, Health: 60,
      Subscriptions: 40, Misc: 20, // Subscriptions + Misc collapse into "Other"
    },
  },
};

// Recharts' <Legend> renders one <svg aria-label="{name} legend icon"> per
// <Bar>, each wrapping a <path> coloured with that Bar's own `fill` prop.
// getAllByLabelText is a real Testing Library query (not raw DOM access);
// reading `fill` out of outerHTML avoids querySelector, which
// testing-library/no-node-access disallows in this file.
function legendFills() {
  return screen.getAllByLabelText(/legend icon$/i).map((svg) => {
    const match = svg.outerHTML.match(/fill="([^"]+)"/);
    return match ? match[1] : null;
  });
}

test('every category series (including Other) gets a distinct fill', () => {
  render(<SpendingByCategoryCard dashboard={dashboard} loading={false} error={null} />);

  const fills = legendFills();

  // TOP_N (8) named categories + one "Other" bucket for the 9th+.
  expect(fills).toHaveLength(9);
  expect(new Set(fills).size).toBe(9);
});

test('"Other" gets its own neutral token, not a positional chart colour', () => {
  render(<SpendingByCategoryCard dashboard={dashboard} loading={false} error={null} />);

  const otherIcon = screen.getByLabelText('Other legend icon');
  expect(otherIcon.outerHTML).toContain('fill="var(--text-faint)"');
});
