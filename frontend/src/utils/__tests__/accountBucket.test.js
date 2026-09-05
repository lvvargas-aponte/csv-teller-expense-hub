import {
  classifyAccountBucket,
  INVESTMENT_SUBTYPES,
  isInstallmentLoan,
  setInstallmentSubtypes,
  setInvestmentSubtypes,
} from '../accountBucket';

// Port of backend `analytics.classify_account_bucket`. The cases below mirror
// its branches one for one so the two suites stay comparable by eye.

afterEach(() => {
  setInvestmentSubtypes(null);
  setInstallmentSubtypes(null);
});

test('a depository account with a retirement subtype is an investment', () => {
  expect(classifyAccountBucket({ type: 'depository', subtype: 'Roth IRA' }))
    .toBe('investment');
});

test('type wins when it is explicitly investment', () => {
  expect(classifyAccountBucket({ type: 'investment', subtype: '' }))
    .toBe('investment');
});

test('a credit card is credit regardless of subtype', () => {
  expect(classifyAccountBucket({ type: 'credit', subtype: 'loan' }))
    .toBe('credit');
});

test('a plain depository account is cash', () => {
  expect(classifyAccountBucket({ type: 'depository', subtype: 'checking' }))
    .toBe('cash');
});

test('anything else is other', () => {
  expect(classifyAccountBucket({ type: 'loan', subtype: '' })).toBe('other');
  expect(classifyAccountBucket({})).toBe('other');
  expect(classifyAccountBucket(null)).toBe('other');
});

test('subtype matching ignores case and surrounding whitespace', () => {
  expect(classifyAccountBucket({ type: 'depository', subtype: '  401K  ' }))
    .toBe('investment');
});

test('the bundled subtype list covers the backend set', () => {
  ['401k', '401(k)', '403b', '403(b)', 'ira', 'roth_ira', 'roth ira',
    'brokerage', 'hsa', 'investment', 'retirement', 'rollover_ira',
    'sep_ira', 'simple_ira', '529',
  ].forEach((s) => expect(INVESTMENT_SUBTYPES.has(s)).toBe(true));
});

test('a fetched server list replaces the bundled one', () => {
  setInvestmentSubtypes(['crypto']);
  expect(classifyAccountBucket({ type: 'depository', subtype: 'crypto' }))
    .toBe('investment');
  // The server is authoritative: a subtype it dropped stops counting.
  expect(classifyAccountBucket({ type: 'depository', subtype: 'roth ira' }))
    .toBe('cash');
});

test('an empty or failed fetch keeps the bundled list', () => {
  setInvestmentSubtypes([]);
  expect(classifyAccountBucket({ type: 'depository', subtype: 'roth ira' }))
    .toBe('investment');
});

test('a home or vehicle is a real asset, never cash', () => {
  expect(classifyAccountBucket({ type: 'asset', subtype: 'home' })).toBe('real_asset');
  expect(classifyAccountBucket({ type: 'asset', subtype: 'vehicle' })).toBe('real_asset');
  expect(classifyAccountBucket({ type: 'asset', subtype: '' })).toBe('real_asset');
});

test('a real asset is not reclassified by an investment subtype', () => {
  // "investment" is in the subtype vocabulary; a house labelled that way is
  // still a house, and must not join the portfolio allocation.
  expect(classifyAccountBucket({ type: 'asset', subtype: 'investment' }))
    .toBe('real_asset');
});

// --- Installment loans --------------------------------------------------
// A loan is credit, but it has no limit to be a percentage of and no balance
// you choose how fast to clear. The backend already splits it out of
// utilization; the frontend needs the same line for the Debt page.

test.each(['loan', 'mortgage', 'student', 'auto', 'MORTGAGE', ' auto '])(
  'subtype %p is an installment loan', (subtype) => {
    expect(isInstallmentLoan({ type: 'credit', subtype })).toBe(true);
  },
);

test.each([
  ['a credit card', { type: 'credit', subtype: 'credit_card' }],
  ['a card with no subtype', { type: 'credit', subtype: '' }],
  ['cash', { type: 'depository', subtype: 'checking' }],
  ['an investment', { type: 'investment', subtype: 'brokerage' }],
  ['a house', { type: 'asset', subtype: 'home' }],
])('%s is not an installment loan', (_label, account) => {
  expect(isInstallmentLoan(account)).toBe(false);
});

// A depository account someone labelled "loan" is still not credit — the
// bucket check has to come first.
test('subtype alone does not make a non-credit account a loan', () => {
  expect(isInstallmentLoan({ type: 'depository', subtype: 'loan' })).toBe(false);
});

test('the server list replaces the bundled one', () => {
  setInstallmentSubtypes(['heloc']);

  expect(isInstallmentLoan({ type: 'credit', subtype: 'heloc' })).toBe(true);
  expect(isInstallmentLoan({ type: 'credit', subtype: 'mortgage' })).toBe(false);
});

test('an empty server list falls back to the bundled one', () => {
  setInstallmentSubtypes([]);

  expect(isInstallmentLoan({ type: 'credit', subtype: 'mortgage' })).toBe(true);
});
