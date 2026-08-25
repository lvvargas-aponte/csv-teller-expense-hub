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

  test.each(['--brand-grad-from', '--brand-grad-to'])(
    // Defined only in :root — held at the same value in both themes on
    // purpose (white-text fills must not shift to the lighter dark-theme
    // blues), so both runs assert against LIGHT rather than the per-theme t.
    'white text on %s clears AA',
    (token) => {
      expect(contrast('#ffffff', LIGHT[token])).toBeGreaterThanOrEqual(4.5);
    },
  );
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

const APP_CSS = fs.readFileSync(path.join(__dirname, '..', '..', 'index.css'), 'utf8');

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
