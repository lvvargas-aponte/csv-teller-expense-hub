import fs from 'fs';
import path from 'path';

const CSS = fs.readFileSync(path.join(__dirname, '..', 'tokens.css'), 'utf8');

function block(selector) {
  const start = CSS.indexOf(selector);
  if (start === -1) throw new Error(`missing block: ${selector}`);
  const open = CSS.indexOf('{', start);
  const close = CSS.indexOf('}', open);
  return CSS.slice(open + 1, close);
}

function tokens(selector) {
  const out = {};
  for (const line of block(selector).split('\n')) {
    const m = line.match(/^\s*(--[\w-]+)\s*:\s*([^;]+);/);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

function srgb(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const m = hex.match(/^#([0-9a-f]{6})$/i);
  if (!m) throw new Error(`not a literal hex: ${hex}`);
  const n = parseInt(m[1], 16);
  return 0.2126 * srgb((n >> 16) & 255)
    + 0.7152 * srgb((n >> 8) & 255)
    + 0.0722 * srgb(n & 255);
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const LIGHT = tokens(':root');
const DARK = tokens('[data-theme="dark"]');

describe.each([['light', LIGHT], ['dark', DARK]])('%s theme', (name, t) => {
  test.each([
    '--text', '--text-secondary', '--text-muted',
    '--good-text', '--bad-text', '--warn-text', '--brand',
  ])('%s clears AA on --surface-card', (token) => {
    expect(contrast(t[token], t['--surface-card'])).toBeGreaterThanOrEqual(4.5);
  });

  test('brand is not a semantic hue', () => {
    expect(t['--brand']).not.toBe(t['--good']);
    expect(t['--brand']).not.toBe(t['--bad']);
    expect(t['--brand']).not.toBe(t['--warn']);
  });

  test('defines the full chart ramp', () => {
    for (let i = 1; i <= 6; i += 1) {
      expect(t[`--chart-${i}`]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  // Restored specifically because a text badge on this pairing (AccountListRow's
  // "Paid off" tag) once fell back to a retired, undercontrast emerald hex
  // instead of these tokens. Locks the pairing itself, not just the badge.
  test('--good-text clears AA on --good-wash', () => {
    expect(contrast(t['--good-text'], t['--good-wash'])).toBeGreaterThanOrEqual(4.5);
  });
});

test.each(['--brand-grad-from', '--brand-grad-to'])(
  'white text on %s clears AA',
  (token) => {
    expect(contrast('#ffffff', LIGHT[token])).toBeGreaterThanOrEqual(4.5);
  },
);

// The whole point of these two tokens: they must NOT follow the theme.
// A dark-mode override would put white text back on #60a5fa (2.54:1).
test('white-text gradient stops are never redefined per theme', () => {
  expect(DARK['--brand-grad-from']).toBeUndefined();
  expect(DARK['--brand-grad-to']).toBeUndefined();
});

test('light theme defines the spacing and type scales once', () => {
  expect(Object.keys(LIGHT).filter((k) => k.startsWith('--space-'))).toHaveLength(8);
  expect(LIGHT['--space-4']).toBe('16px');
  expect(LIGHT['--text-base']).toBe('13px');
});

test('legacy aliases point at new primitives, not raw hex', () => {
  for (const alias of ['--bg-root', '--bg-card', '--accent', '--text-primary']) {
    expect(LIGHT[alias]).toMatch(/^var\(--[\w-]+\)$/);
  }
});

const APP_CSS = [
  'base.css', 'shell.css', 'transactions.css', 'debt.css',
  'accounts.css', 'finances.css', 'settings.css', 'a11y.css',
].map((f) => fs.readFileSync(path.join(__dirname, '..', f), 'utf8')).join('\n');

describe('brand and semantic colours stay separate', () => {
  test.each([
    '.eh-kpi-value--pos',
    '.tx-amt-val--credit',
    '.ov-bal-primary--pos',
    '.acct-row-balance.is-positive',
  ])('%s uses the good token, not the brand', (selector) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rules = APP_CSS.match(new RegExp(`${escaped}\\s*\\{[^}]*\\}`, 'g'));
    expect(rules).not.toBeNull();
    for (const rule of rules) {
      expect(rule).toContain('var(--good-text)');
      expect(rule).not.toContain('var(--accent)');
    }
  });
});

// Every sheet except tokens.css, which is excluded on purpose: it legitimately
// holds #059669/#ecfdf5/#34d399/#6ee7b7 (and their dark counterparts) as the
// literal definitions of --good/--good-wash/--good-text. It's the one file
// whose entire job is to hold literals; retiring green as brand doesn't mean
// retiring it as the financial-positive colour, which still lives here.
const ALL_SHEETS = [
  'base.css', 'shell.css', 'transactions.css', 'debt.css',
  'accounts.css', 'finances.css', 'settings.css', 'a11y.css', 'shared-page.css',
].map((f) => fs.readFileSync(path.join(__dirname, '..', f), 'utf8')).join('\n');

describe('the emerald brand residue does not come back', () => {
  const GREEN_LITERALS = [
    '#34d399', '#10b981', '#6ee7b7', '#ecfdf5', '#064e3b',
    '#0f2417', '#1a3a27', '#a7f3d0', '#d1fae5', '#f0fdf4', '#059669',
  ];

  // .tx-adj-quick is the one deliberate exception: tokenising the fill would
  // leave mint text on a near-white background in dark mode, so it stays
  // literal in both themes. Strip it out before scanning for the rest.
  const SCAN_TARGET = ALL_SHEETS.replace(
    /\.tx-adj-quick\s*\{[^}]*\}/,
    '',
  ).replace(
    /\.tx-adj-quick:hover\s*\{[^}]*\}/,
    '',
  );

  test.each(GREEN_LITERALS)('%s does not appear outside the pale-green-pill exception', (hex) => {
    expect(SCAN_TARGET).not.toContain(hex);
  });

  test('the exception itself is still there, so the strip above is real', () => {
    expect(ALL_SHEETS).toContain('#ecfdf5'); // .tx-adj-quick fill
  });

  test('no emerald-tinted shadow survives', () => {
    expect(ALL_SHEETS).not.toMatch(/rgba\(\s*5,\s*150,\s*105/);
  });

  // rgba forms of the same emerald family (tailwind emerald-500 and
  // emerald-400) can carry the hue just as well as a hex literal and the
  // checks above are blind to them. #34d399 == rgb(52,211,153) and
  // #10b981 == rgb(16,185,129) — round 1 of review found a dozen of these
  // hiding in translucent fills the hex scan never saw.
  test.each(['16, *185, *129', '52, *211, *153'])('no rgba(%s, …) emerald tint survives', (channels) => {
    expect(SCAN_TARGET).not.toMatch(new RegExp(`rgba\\(\\s*${channels}`));
  });
});

describe('the brand gradient lives in one token', () => {
  test('no rule hand-rolls a blue-violet gradient', () => {
    const handRolled = APP_CSS.match(/linear-gradient\([^)]*#(2563eb|7c3aed|60a5fa|a78bfa)/gi);
    expect(handRolled).toBeNull();
  });

  test('the banner uses the gradient token', () => {
    const rule = APP_CSS.match(/\.eh-banner\s*\{[^}]*\}/);
    expect(rule).not.toBeNull();
    expect(rule[0]).toContain('var(--brand-gradient)');
  });

  test('no emerald gradient survives', () => {
    expect(APP_CSS).not.toMatch(/linear-gradient\([^)]*#(059669|065f46)/i);
  });
});

// Phase 8 Task 3: the last raw hex sitting in component JSX/inline styles,
// tokenized by role (brand vs good/bad/warn vs border/faint text). This is
// the guard that stops the next feature from reintroducing a literal hex
// where a token belongs.
//
// components/settings/categoryColor.js and utils/institutionColor.js are
// EXCLUDED ON PURPOSE: they are generated data palettes that assign an
// arbitrary distinguishable colour per category/institution. That's data,
// not theme — tokenizing them would collapse distinct categories onto the
// same six chart hues, which is a regression, not a fix. They are never
// read by this test.
const COMPONENT_FILES = [
  'components/accounts/AccountRow.js',
  'components/accounts/BrokerageRow.js',
  'components/finances/BudgetPresetModal.js',
  'components/finances/BudgetsSection.js',
  'components/finances/DashboardTab.js',
  'components/finances/GoalsSection.js',
  'components/finances/InvestmentsTab.js',
  'components/finances/KnowledgeSection.js',
  'components/finances/PortfolioQuality.js',
  'components/finances/SubscriptionsSection.js',
  'components/finances/cards/BudgetsCard.js',
  'components/finances/cards/CashFlowCard.js',
  'components/finances/cards/CreditUtilizationCard.js',
  'components/finances/cards/GoalsCard.js',
  'components/finances/cards/NetWorthCard.js',
  'components/finances/cards/RecurringChargesCard.js',
  'components/finances/cards/SpendingByCategoryCard.js',
  'components/finances/cards/UpcomingBillsCard.js',
  'components/finances/payoff/AprCell.js',
  'components/finances/payoff/PayoffForm.js',
  'components/finances/payoff/PayoffResults.js',
  'components/transactions/ControlBar.js',
  'components/transactions/SuggestPreviewModal.js',
  'components/transactions/TransferExpandRow.js',
  'components/transactions/UploadCsvModal.js',
];

describe('no raw hex or rgb() literals remain in the tokenized components', () => {
  // A hex guard alone misses rgb()/rgba() forms of the same colours — round
  // 1 of the CSS-sheet pass (tokens.test.js above) found a dozen of those
  // hiding in translucent fills the hex scan never saw. Cover both forms
  // here too, even though none of these 25 files currently use rgba() —
  // color-mix(var(--token) ..., transparent) replaced every translucent fill.
  const HEX_RE = /#[0-9a-fA-F]{3,6}\b/;
  const RGB_LITERAL_RE = /rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+/;

  test.each(COMPONENT_FILES)('%s has no raw hex or rgb() literal', (relPath) => {
    const src = fs.readFileSync(path.join(__dirname, '..', '..', relPath), 'utf8');
    expect(src).not.toMatch(HEX_RE);
    expect(src).not.toMatch(RGB_LITERAL_RE);
  });
});
