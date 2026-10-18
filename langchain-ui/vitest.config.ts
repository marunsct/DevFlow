import { defineConfig } from 'vitest/config';

// Apart from vite.config.ts: the tests need no plugins, and keeping them out of
// that file keeps the application's build free of the test runner's own types.
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
  },
});
