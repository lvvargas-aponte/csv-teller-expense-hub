import { resolveLegacyRoute, pathForTab, ACTIVE_TAB_KEY } from '../legacyRoutes';

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    removeItem: (k) => { delete data[k]; },
    has: (k) => k in data,
  };
}

test('returns null when there is nothing stored', () => {
  expect(resolveLegacyRoute(fakeStorage())).toBeNull();
});

test.each([
  ['dashboard', '/'],
  ['accounts', '/accounts'],
  ['investments', '/invest'],
  ['budgets', '/plan/budgets'],
  ['goals', '/plan/goals'],
  ['commitments', '/plan/commitments'],
  ['advisor', '/ask'],
  ['knowledge', '/ask/memory'],
  ['settings', '/settings'],
])('maps the stored tab %s to %s', (stored, path) => {
  expect(resolveLegacyRoute(fakeStorage({ [ACTIVE_TAB_KEY]: stored }))).toBe(path);
});

test.each([
  ['bills', '/plan/commitments'],
  ['subscriptions', '/plan/commitments'],
  ['overview', '/'],
])('maps the retired tab %s to %s', (stored, path) => {
  expect(resolveLegacyRoute(fakeStorage({ [ACTIVE_TAB_KEY]: stored }))).toBe(path);
});

test('an unrecognised tab goes home rather than nowhere', () => {
  expect(resolveLegacyRoute(fakeStorage({ [ACTIVE_TAB_KEY]: 'wat' }))).toBe('/');
});

test('clears the key so the migration runs once', () => {
  const storage = fakeStorage({ [ACTIVE_TAB_KEY]: 'accounts' });
  resolveLegacyRoute(storage);
  expect(storage.has(ACTIVE_TAB_KEY)).toBe(false);
  expect(resolveLegacyRoute(storage)).toBeNull();
});

describe('pathForTab', () => {
  test.each([
    ['accounts', '/accounts'],
    ['bills', '/plan/commitments'],
    ['advisor', '/ask'],
  ])('maps %s to %s', (tabId, path) => {
    expect(pathForTab(tabId)).toBe(path);
  });

  test('an unknown id from the server falls back to Home, never undefined', () => {
    // Alert targets come from the API, so the id set is not knowable here.
    expect(pathForTab('something-new')).toBe('/');
    expect(pathForTab(undefined)).toBe('/');
  });
});

test('survives storage that throws (private mode)', () => {
  const hostile = {
    getItem: () => { throw new Error('denied'); },
    removeItem: () => { throw new Error('denied'); },
  };
  expect(() => resolveLegacyRoute(hostile)).not.toThrow();
  expect(resolveLegacyRoute(hostile)).toBeNull();
});
