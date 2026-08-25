import { webcrypto } from 'node:crypto';
import '@testing-library/jest-dom';
import { toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

// jsdom exposes no Web Crypto; components that mint local ids with
// crypto.randomUUID() would throw on render.
if (!global.crypto?.randomUUID) {
  Object.defineProperty(global, 'crypto', { value: webcrypto, configurable: true });
}
