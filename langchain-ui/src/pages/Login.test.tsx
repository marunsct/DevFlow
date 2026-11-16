import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

// Found in a review: the page said "Default credentials: admin / admin", which the server never sets - the first
// administrator's password comes from ADMIN_PASSWORD (or is generated) - so a new user's first action failed.
describe('the sign-in page', () => {
  it('says where the first password comes from and claims no default one', () => {
    render(<MemoryRouter><Login /></MemoryRouter>);
    expect(screen.queryByText(/admin \/ admin/)).toBeNull();
    expect(screen.getByText(/ADMIN_PASSWORD/)).toBeTruthy();
  });
});
