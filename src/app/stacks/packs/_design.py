"""The design tokens every web pack's stylesheet starts with (owner decision 2026-10-18, plan item A).

Products started from browser defaults: unstyled controls, no focus ring, and
text colours a contrast audit could fail. These are a small accessible set -
colours that pass WCAG AA on their own background in both schemes, a spacing
and type scale, and a visible focus ring - as CSS custom properties, so a
product can change any value without hunting for it. The names are the
contract; the values are the product's to change.
"""

from __future__ import annotations

DESIGN_TOKENS = """/* Design tokens: change the values to suit the product; use the names
   (var(--color-text), var(--space-3)) rather than raw values. */
:root {
  color-scheme: light dark;
  --color-bg: #ffffff;
  --color-surface: #f4f5f7;
  --color-text: #1b1f24;
  --color-muted: #57606a;
  --color-border: #d0d7de;
  --color-primary: #0b5cad;
  --color-on-primary: #ffffff;
  --color-danger: #b42318;
  --color-success: #1a7f37;
  --color-focus: #0b5cad;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --font-sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --font-size-sm: 0.875rem;
  --font-size-md: 1rem;
  --font-size-lg: 1.25rem;
  --font-size-xl: 1.75rem;
  --radius: 0.375rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0d1117;
    --color-surface: #161b22;
    --color-text: #e6edf3;
    --color-muted: #9da7b3;
    --color-border: #30363d;
    --color-primary: #4493f8;
    --color-on-primary: #0d1117;
    --color-danger: #f47067;
    --color-success: #57ab5a;
    --color-focus: #4493f8;
  }
}

body {
  background: var(--color-bg);
  color: var(--color-text);
}

button, input, select, textarea {
  font: inherit;
}

:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

"""
