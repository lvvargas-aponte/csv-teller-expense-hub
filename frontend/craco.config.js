module.exports = {
  jest: {
    configure: {
      setupFilesAfterEnv: [
        '<rootDir>/src/test-config/setupTests.js',
      ],
      moduleNameMapper: {
        // Pure-ESM dep that CRA's jest transform can't parse — see the stub.
        '^react-markdown$': '<rootDir>/src/test-config/reactMarkdownStub.js',
      },
    },
  },
};
