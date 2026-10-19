import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FileDiffs } from './FileDiffs';

const DIFF = [
  'diff --git a/app/auth.py b/app/auth.py',
  '--- a/app/auth.py',
  '+++ b/app/auth.py',
  '@@ -1,2 +1,3 @@',
  '-def sign_in(): pass',
  '+def sign_in(user):',
  '+    return session(user)',
  'diff --git a/web/src/Login.tsx b/web/src/Login.tsx',
  '--- a/web/src/Login.tsx',
  '+++ b/web/src/Login.tsx',
  '@@ -3 +3 @@',
  "+export const Login = () => null;",
].join('\n');

describe('a commit, file by file', () => {
  it('folds each file under its name and its lines added and removed', () => {
    render(<FileDiffs text={DIFF} />);
    expect(screen.getByText('2 files')).toBeTruthy();
    expect(screen.getByText('app/auth.py')).toBeTruthy();
    expect(screen.getByText('web/src/Login.tsx')).toBeTruthy();
    expect(screen.getByText('+2')).toBeTruthy();
    expect(screen.getByText('−1')).toBeTruthy();
    expect(screen.getByText('+1')).toBeTruthy();
  });

  it('shows a one-file change as it is', () => {
    render(<FileDiffs text={DIFF.split('\n').slice(0, 7).join('\n')} />);
    expect(screen.queryByText(/files$/)).toBeNull();
    expect(screen.getByText('+def sign_in(user):')).toBeTruthy();
  });
});
