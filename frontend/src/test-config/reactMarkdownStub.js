// react-markdown v9 ships as pure ESM, which CRA's jest transform skips
// (node_modules is not transformed by default). Transforming it instead
// would mean allowlisting its ~40-package ESM dependency tree
// (remark-*, micromark*, unified, vfile, hast-*, mdast-*, …) and keeping
// that list in sync on every upgrade.
//
// No test asserts on rendered markdown — AdvisorChat is the only consumer,
// and its tests cover message flow, not formatting — so the render path is
// stubbed to plain text. If a test ever needs real markdown output, drop
// this mapping for that suite rather than expanding the stub.
const React = require('react');

module.exports = function ReactMarkdown({ children }) {
  return React.createElement('div', { 'data-testid': 'markdown' }, children);
};
