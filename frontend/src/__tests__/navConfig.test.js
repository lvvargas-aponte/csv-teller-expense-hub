import { NAV, ALL_PATHS, findSection } from '../navConfig';
import { ICON_NAMES } from '../components/ui/Icon';

test('ships the eight destinations in order', () => {
  expect(NAV.map((s) => s.id)).toEqual([
    'home', 'transactions', 'accounts', 'debt', 'invest', 'plan', 'ask', 'settings',
  ]);
});

test('every icon name resolves to a real icon', () => {
  for (const section of NAV) {
    expect(ICON_NAMES).toContain(section.icon);
  }
});

test('Commitments does not reuse the History glyph', () => {
  // A backward-facing clock for forward-looking commitments read as "past",
  // and collided with the genuinely past-facing History view.
  const plan = NAV.find((s) => s.id === 'plan');
  const commitments = plan.children.find((c) => c.id === 'commitments');
  expect(commitments.icon).not.toBe('history');
});

test('every path is unique', () => {
  expect(new Set(ALL_PATHS).size).toBe(ALL_PATHS.length);
});

test('ALL_PATHS flattens grandchildren, not just children', () => {
  expect(ALL_PATHS).toContain('/plan/commitments/due');
  expect(ALL_PATHS).toContain('/plan/commitments/recurring');
});

test('child paths are nested under their parent', () => {
  for (const section of NAV) {
    for (const child of section.children ?? []) {
      expect(child.path.startsWith(section.path)).toBe(true);
    }
  }
});

describe('findSection', () => {
  test.each([
    ['/', 'home'],
    ['/transactions', 'transactions'],
    ['/transactions/shared', 'transactions'],
    ['/transactions/history', 'transactions'],
    ['/accounts', 'accounts'],
    ['/plan/budgets', 'plan'],
    ['/settings/connections', 'settings'],
  ])('%s belongs to %s', (pathname, id) => {
    expect(findSection(pathname).id).toBe(id);
  });

  test('an unknown path belongs to no section', () => {
    expect(findSection('/nope')).toBeUndefined();
  });

  test('does not match a path that merely shares a prefix', () => {
    expect(findSection('/accountsomething')).toBeUndefined();
  });
});
