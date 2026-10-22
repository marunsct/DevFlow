// Every test starts with empty storage and no stored appearance.
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.removeAttribute('data-accent');
  document.documentElement.setAttribute('data-theme', 'graphite');
});
