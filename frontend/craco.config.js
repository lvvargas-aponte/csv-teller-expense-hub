// `jest.configure` must be the FUNCTION form. Given a plain object, craco
// merges arrays by concatenation, so CRA's own entries survive alongside ours
// — which matters for moduleNameMapper ordering and would silently defeat any
// attempt to override transformIgnorePatterns.
module.exports = {
  jest: {
    configure: (jestConfig) => ({
      ...jestConfig,
      setupFilesAfterEnv: [
        '<rootDir>/src/test-config/setupTests.js',
      ],
      moduleNameMapper: {
        ...jestConfig.moduleNameMapper,
        // react-markdown 9 is ESM-only with conditional exports Jest's CJS
        // resolver cannot follow. See the stub for why we don't transpile the
        // dependency chain instead.
        '^react-markdown$': '<rootDir>/src/test-config/reactMarkdownStub.js',
      },
    }),
  },
};
