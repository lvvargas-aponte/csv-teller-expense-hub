module.exports = {
  jest: {
    configure: {
      setupFilesAfterEnv: [
        '<rootDir>/src/test-config/setupTests.js',
      ],
    },
  },
};
