// Test stub for react-markdown.
//
// react-markdown 9 and its unified/remark/micromark dependency chain are
// ESM-only and lean on conditional `exports` subpaths that Jest's CJS
// resolver can't follow (it dies on things like
// 'unist-util-visit-parents/do-not-use-color'). Transpiling the whole chain
// is possible but means maintaining an allow-list of ~30 transitive packages
// that changes on every upgrade.
//
// Nothing in the suite asserts rendered markdown — AdvisorChat has no test of
// its own, and App.test.js only needs the import to resolve. So we render the
// markdown source as plain text and move on. If markdown rendering ever needs
// real coverage, test it in isolation with a proper ESM setup rather than
// unpicking this.
import React from 'react';

export default function ReactMarkdown({ children }) {
  return <div data-testid="react-markdown">{children}</div>;
}
