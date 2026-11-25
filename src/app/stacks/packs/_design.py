"""The design tokens and base element styles every web pack's stylesheet starts with.

Products started from browser defaults: unstyled controls, no focus ring, and text colours a contrast audit could fail
(owner decision 2026-10-18, plan item A). The tokens are a small accessible set - colours that pass WCAG AA on their
own background in both schemes, a spacing and type scale, and a visible focus ring - as CSS custom properties, so a
product can change any value without hunting for it. The names are the contract; the values are the product's to
change.

The tokens alone were a minimum: read in eight stored products (plan PQ.7), the pages were correct but plain - a bare
heading, stacked fields and a ruled list, no surface, no states beyond opacity. So the stylesheet also styles plain,
unclassed markup on those tokens: the page surface and its header, form fields with their hover, focus, disabled and
invalid states, a primary and a quiet control, a list row, a message area and an empty-state block (an element with
the ARIA role `alert` or `status`), elevation and one transition. Element and attribute selectors only - no class a
product must know of - so a builder writing plain markup gets a designed page, and nothing here hides content or
sets a width a phone cannot hold.
"""

from __future__ import annotations

from pathlib import Path

#: The custom properties: what a product changes to restyle itself.
TOKENS = """/* Design tokens: change the values to suit the product; use the names
   (var(--color-text), var(--space-3)) rather than raw values. Below them,
   plain markup is styled on these tokens: write a <header>, a <form>, a
   list and an element with role="status" or role="alert", and it is designed. */
:root {
  color-scheme: light dark;
  --color-bg: #ffffff;
  --color-surface: #f4f5f7;
  --color-text: #1b1f24;
  --color-muted: #57606a;
  --color-border: #d0d7de;
  --color-primary: #0b5cad;
  --color-primary-hover: #094c8f;
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
  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.08), 0 1px 3px rgb(0 0 0 / 0.06);
  --shadow-2: 0 4px 12px rgb(0 0 0 / 0.12);
  --transition: 120ms ease-out;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0d1117;
    --color-surface: #161b22;
    --color-text: #e6edf3;
    --color-muted: #9da7b3;
    --color-border: #30363d;
    --color-primary: #4493f8;
    --color-primary-hover: #6aa9fa;
    --color-on-primary: #0d1117;
    --color-danger: #f47067;
    --color-success: #57ab5a;
    --color-focus: #4493f8;
    --shadow-1: 0 1px 2px rgb(0 0 0 / 0.5);
    --shadow-2: 0 4px 12px rgb(0 0 0 / 0.6);
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

#: Plain markup styled on the tokens (plan PQ.7), kept as the stylesheet it is: element and attribute selectors only.
ELEMENTS = "\n" + Path(__file__).with_name("base_elements.css").read_text(encoding="utf-8")

#: What every web pack's stylesheet starts with: the tokens, then plain markup styled on them.
DESIGN_TOKENS = TOKENS + ELEMENTS
