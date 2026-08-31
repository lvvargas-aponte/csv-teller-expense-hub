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
  'accounts.css', 'finances.css', 'settings.css', 'a11y.css', 'shared-page.css',
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

// Phase 8 Task 4b: every hardcoded colour in the nine stylesheets gets
// mapped to a token by role. This is the general guard the green-only one
// above (Task 2) and the component-file one below (Task 3) were each a
// narrower version of — it catches any six-digit hex surviving anywhere in
// the sheets, not just the emerald family, so the next stray literal (of
// any hue) fails CI instead of quietly landing.
describe('no raw hex literal remains in the nine stylesheets', () => {
  const HEX_RE = /#[0-9a-fA-F]{3,6}\b/g;

  // Every survivor must be named here, with why it's allowed to stay.
  const ALLOWED = new Set([
    // .tx-adj-quick (transactions.css ~L671-681) is the one sanctioned
    // exception in the whole migration: tokenising the fill would leave
    // mint text on a near-white background in dark mode, so its pale-green
    // pill (fill, text and border, plus the hover shade) stays literal in
    // both themes on purpose. See the comment on that rule.
    '#ecfdf5', '#047857', '#a7f3d0', '#d1fae5',
  ]);

  test('every hex literal left in the sheets is on the allow-list', () => {
    const found = new Set((ALL_SHEETS.match(HEX_RE) || []).map((h) => h.toLowerCase()));
    const unexpected = [...found].filter((h) => !ALLOWED.has(h));
    expect(unexpected).toEqual([]);
  });

  test('the allow-list has no stale entries', () => {
    const found = new Set((ALL_SHEETS.match(HEX_RE) || []).map((h) => h.toLowerCase()));
    for (const hex of ALLOWED) {
      expect(found.has(hex)).toBe(true);
    }
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
// tokenized by role (brand vs good/bad/warn vs border/faint text). This
// guard used to scan a hard-coded 25-file list — a real instance
// (SuggestedSeeds.js's `color: '#fff'`) sat one directory below that list
// and passed CI for the rest of the phase. Widen the scope to every
// component file instead of growing the list, so the *next* stray literal
// can't hide by simply living outside whatever files someone remembered to
// name.
//
// components/settings/categoryColor.js is EXCLUDED ON PURPOSE: it's a
// generated data palette that assigns an arbitrary distinguishable colour
// per category. That's data, not theme — tokenizing it would collapse
// distinct categories onto the same six chart hues, which is a regression,
// not a fix. (utils/institutionColor.js is the same kind of exception, but
// it lives outside src/components entirely, so this components-scoped scan
// never reaches it.)
function collectComponentFiles(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__') continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) collectComponentFiles(p, out);
    else if (/\.jsx?$/.test(entry.name)) out.push(p);
  }
  return out;
}

const COMPONENTS_ROOT = path.join(__dirname, '..', '..', 'components');
const EXCLUDED_COMPONENT_FILES = new Set([
  path.join(COMPONENTS_ROOT, 'settings', 'categoryColor.js'),
]);
const COMPONENT_FILES = collectComponentFiles(COMPONENTS_ROOT, [])
  .filter((f) => !EXCLUDED_COMPONENT_FILES.has(f))
  .map((f) => path.relative(path.join(__dirname, '..', '..'), f));

describe('no raw hex or rgb() literals remain in the tokenized components', () => {
  // A hex guard alone misses rgb()/rgba() forms of the same colours — round
  // 1 of the CSS-sheet pass (tokens.test.js above) found a dozen of those
  // hiding in translucent fills the hex scan never saw. Cover both forms
  // here too, even though none of these files currently use rgba() —
  // color-mix(var(--token) ..., transparent) replaced every translucent fill.
  const HEX_RE = /#[0-9a-fA-F]{3,6}\b/;
  const RGB_LITERAL_RE = /rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+/;

  test('scan covers every non-excluded component file (guard against an empty walk)', () => {
    expect(COMPONENT_FILES.length).toBeGreaterThan(24);
  });

  test.each(COMPONENT_FILES)('%s has no raw hex or rgb() literal', (relPath) => {
    const src = fs.readFileSync(path.join(__dirname, '..', '..', relPath), 'utf8');
    expect(src).not.toMatch(HEX_RE);
    expect(src).not.toMatch(RGB_LITERAL_RE);
  });
});

// Phase 8 final fix wave — Important 3: the general hex/rgb guards above are
// each scoped to a hue or a value form. Named CSS colour keywords (`white`,
// `black`, …) are neither, so the literal `color: white` on .tx-note-save
// sailed through every one of them. Scope this to declaration *values* only
// (selectors and property names — e.g. `white-space`, `.acct-status-red` —
// are stripped first) and to values with `var(...)` references removed
// first too, since `color: var(--red)` legitimately contains the word "red".
describe('no CSS named colour keyword remains in the nine stylesheets', () => {
  const NAMED_COLOURS = /\b(white|black|red|blue|green|yellow|orange|purple|gray|grey|navy|teal|pink|brown|cyan|magenta|indigo|violet|silver|gold)\b/i;

  function declarationValues(css) {
    const blocks = css.match(/\{[^{}]*\}/g) || [];
    const values = [];
    for (const b of blocks) {
      for (const decl of b.slice(1, -1).split(';')) {
        const idx = decl.indexOf(':');
        if (idx !== -1) values.push(decl.slice(idx + 1));
      }
    }
    return values.join('\n').replace(/var\([^)]*\)/g, '');
  }

  test('no declaration value uses a bare colour keyword', () => {
    expect(declarationValues(ALL_SHEETS)).not.toMatch(NAMED_COLOURS);
  });
});

// Important 3(b): the emerald-family rgba() guard above only recognises two
// specific channel triples. It's blind to an rgba() of any other hue (e.g.
// a stray rgba(59,130,246,…) blue) landing as a literal instead of a token.
// Widen it to assert every rgb()/rgba() triple in the sheets is achromatic
// (pure black or pure white, used for shadows/overlays that don't carry
// brand or semantic meaning) — anything else is a colour that should be a
// token. transactions.css's .tx-detail-grid .seg--active shadow used to be
// rgba(15,23,42,0.14) — a literal near-black-navy tint that skipped the
// dark-theme shadow flip in tokens.css — and is the live instance this
// closes; it now reads var(--shadow-sm).
describe('no non-achromatic rgb()/rgba() literal remains in the nine stylesheets', () => {
  const ALLOWED_TRIPLES = new Set(['0,0,0', '255,255,255']);

  test('every rgb()/rgba() triple is black or white', () => {
    const found = new Set();
    const re = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/g;
    let m;
    while ((m = re.exec(ALL_SHEETS))) found.add(`${m[1]},${m[2]},${m[3]}`);
    const unexpected = [...found].filter((t) => !ALLOWED_TRIPLES.has(t));
    expect(unexpected).toEqual([]);
  });
});

// Important 3(c) — the highest-value hole: nothing previously checked that a
// var(--x) referenced anywhere actually resolves to a real definition in
// tokens.css. This is the guard that would have caught --bg-muted and
// --bg-subtle (defined nowhere, silently falling back to their inline
// fallback value) the moment they were introduced, instead of at a
// whole-phase review four instances later.
describe('every var(--x) reference resolves to a token definition', () => {
  // --chart- is a documented exception: RecurringChargesCard.js builds the
  // reference dynamically (`var(--chart-${n})`), so the static scan below
  // only ever sees the literal prefix, not a real property name. --chart-1
  // through --chart-8 are separately locked by "defines the full chart
  // ramp" above.
  const ALLOWED_UNRESOLVED = new Set(['--chart-']);

  function stripComments(src, isJs) {
    let out = src.replace(/\/\*[\s\S]*?\*\//g, '');
    if (isJs) out = out.replace(/\/\/.*$/gm, '');
    return out;
  }

  // __tests__ is skipped: this describe block's own title strings contain
  // the literal text "var(--x)" for documentation purposes, which isn't a
  // real reference — scanning test files would flag the guard's own prose.
  function collectSrcFiles(dir, out) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '__tests__') continue;
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) collectSrcFiles(p, out);
      else if (/\.(jsx?|css)$/.test(entry.name)) out.push(p);
    }
    return out;
  }

  test('every referenced custom property is defined in tokens.css', () => {
    const srcRoot = path.join(__dirname, '..', '..');
    const files = collectSrcFiles(srcRoot, []);
    const used = new Set();
    for (const f of files) {
      const raw = fs.readFileSync(f, 'utf8');
      const src = stripComments(raw, /\.jsx?$/.test(f));
      const re = /var\(\s*(--[\w-]+)/g;
      let m;
      while ((m = re.exec(src))) used.add(m[1]);
    }

    const defined = new Set();
    const defRe = /(--[\w-]+)\s*:/g;
    let m;
    while ((m = defRe.exec(CSS))) defined.add(m[1]);

    const missing = [...used].filter(
      (v) => !defined.has(v) && !ALLOWED_UNRESOLVED.has(v),
    );
    expect(missing).toEqual([]);
  });

  test('the allow-list exception is still exercised, so the strip above is real', () => {
    expect(fs.readFileSync(
      path.join(__dirname, '..', '..', 'components', 'finances', 'cards', 'RecurringChargesCard.js'),
      'utf8',
    )).toContain('var(--chart-${');
  });
});
