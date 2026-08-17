import { reconcile, DEFAULT_LAYOUT } from '../useDashboardLayout';

const ids = (layout) => layout.map((item) => item.i);

test('an empty saved layout falls back to the default arrangement', () => {
  expect(reconcile([])).toBe(DEFAULT_LAYOUT);
  expect(reconcile(undefined)).toBe(DEFAULT_LAYOUT);
  expect(reconcile(null)).toBe(DEFAULT_LAYOUT);
});

test('a saved arrangement is preserved', () => {
  const saved = [
    { i: 'alerts', x: 0, y: 0, w: 12, h: 6 },
    { i: 'net_worth', x: 0, y: 6, w: 12, h: 8 },
  ];
  expect(ids(reconcile(saved)).slice(0, 2)).toEqual(['alerts', 'net_worth']);
});

test('a card that shipped after the layout was saved is appended, not dropped', () => {
  // The failure this prevents: a user who arranged their dashboard before
  // Goals existed would never see Goals, with no indication why.
  const saved = [{ i: 'net_worth', x: 0, y: 0, w: 12, h: 8 }];
  const result = reconcile(saved);

  expect(ids(result)).toContain('goals');
  expect(ids(result)).toHaveLength(DEFAULT_LAYOUT.length);
  expect(ids(result)[0]).toBe('net_worth');
});

test('appended cards land below everything already placed', () => {
  const saved = [{ i: 'net_worth', x: 0, y: 0, w: 12, h: 8 }];
  const result = reconcile(saved);
  const appended = result.filter((item) => item.i !== 'net_worth');

  expect(appended.every((item) => item.y >= 8)).toBe(true);
});

test('an id that no longer exists is discarded', () => {
  const saved = [
    { i: 'net_worth', x: 0, y: 0, w: 12, h: 8 },
    { i: 'card_that_was_removed', x: 0, y: 8, w: 6, h: 4 },
  ];
  expect(ids(reconcile(saved))).not.toContain('card_that_was_removed');
});
