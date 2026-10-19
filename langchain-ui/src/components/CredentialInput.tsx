import React from 'react';
import { Field } from '../ui';

/**
 * A stored secret's field: says whether one is stored (with its hint, never the
 * value), and leaves it as it is when left empty. Defined at module level: built
 * inside the Settings render, it was a new component on every keystroke, so the
 * input was replaced and lost focus after each character typed.
 */
export const CredentialInput: React.FC<{
  label: string;
  configured: boolean;
  hint?: string | null;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}> = ({ label, configured, hint, placeholder, value, onChange }) => (
  <Field
    label={label}
    aside={<span className={configured ? 'font-mono text-success' : undefined}>{configured ? (hint ?? 'configured') : 'not configured'}</span>}
  >
    {(wiring) => (
      <input
        {...wiring}
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary font-mono focus:outline-none focus:border-primary"
        placeholder={configured ? 'Leave blank to keep the stored key' : placeholder}
      />
    )}
  </Field>
);
