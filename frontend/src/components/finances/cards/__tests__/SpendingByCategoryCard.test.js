import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

// The drill-down is what fills the card's height, so it lists every category
// the month has — not the chart's top-8 + "Other", which would hide the very
// rows a drill-down exists to show.
const twoMonths = {
  months: ['2026-06', '2026-07'],
  spending_by_month: {
    '2026-06': { Groceries: 400, Dining: 200, Transport: 100 },
    '2026-07': { Groceries: 500, Dining: 100, Transport: 100, Health: 50 },
  },
};

// The chart's own category filter is a <ul> of <li> too, so every breakdown
// assertion scopes to the labelled list rather than to every listitem on screen.
const breakdown = () =>
  within(screen.getByRole('list', { name: 'Category breakdown' })).getAllByRole('listitem');

test('drill-down lists the latest month, ranked, with a total', () => {
  render(<SpendingByCategoryCard dashboard={twoMonths} loading={false} error={null} />);

  expect(screen.getByRole('combobox', { name: 'Month to break down' })).toHaveValue('2026-07');
  expect(screen.getByText('$750.00')).toBeInTheDocument();

  const names = breakdown().map((li) => li.textContent);
  expect(names[0]).toContain('Groceries');
  expect(names[names.length - 1]).toContain('Health');
});

test('each row reports its move against the prior month', () => {
  render(<SpendingByCategoryCard dashboard={twoMonths} loading={false} error={null} />);

  const row = (name) => breakdown().find((li) => li.textContent.includes(name));

  expect(row('Groceries')).toHaveTextContent('↑ 25%');
  expect(row('Dining')).toHaveTextContent('↓ 50%');
  expect(row('Transport')).toHaveTextContent('Flat');
  // Absent in June, so there is no percentage to move by.
  expect(row('Health')).toHaveTextContent('New');
});

test('picking another month rebuilds the breakdown', async () => {
  const user = userEvent.setup();
  render(<SpendingByCategoryCard dashboard={twoMonths} loading={false} error={null} />);

  await user.selectOptions(
    screen.getByRole('combobox', { name: 'Month to break down' }),
    '2026-06',
  );

  expect(screen.getByText('$700.00')).toBeInTheDocument();
  // Health has no June row, and June is the first month in the window, so
  // nothing in the breakdown has a prior month to move against.
  expect(breakdown().map((li) => li.textContent).join(' ')).not.toContain('Health');
  expect(breakdown().map((li) => li.textContent).join(' ')).not.toMatch(/[↑↓]|New|Flat/);
});

test('a month with no spending says so instead of rendering an empty list', () => {
  render(
    <SpendingByCategoryCard
      dashboard={{ months: ['2026-06', '2026-07'], spending_by_month: { '2026-06': { Groceries: 10 }, '2026-07': {} } }}
      loading={false}
      error={null}
    />,
  );

  expect(screen.getByText('No spending in July 2026.')).toBeInTheDocument();
});
