import { describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import Signup from './Signup';

describe('Signup', () => {
  it('submits the form to /api/auth/signup/ with the typed values', async () => {
    const onSignup = vi.fn().mockResolvedValue({});
    const { user } = renderWithProviders(<Signup onSignup={onSignup} />);

    await user.type(
      screen.getByLabelText(/family called/i),
      'The Sageb Family',
    );
    await user.type(screen.getByLabelText(/head scribe/i), 'Mike');
    await user.type(screen.getByLabelText(/sign-in name/i), 'mike');
    await user.type(screen.getByLabelText(/secret word/i), 'ApbBy1!Strong');
    await user.click(screen.getByRole('button', { name: /found a family/i }));

    await waitFor(() => expect(onSignup).toHaveBeenCalledTimes(1));
    expect(onSignup.mock.calls[0][0]).toEqual({
      username: 'mike',
      password: 'ApbBy1!Strong',
      display_name: 'Mike',
      family_name: 'The Sageb Family',
    });
  });

  it('shows the inline error when the API rejects', async () => {
    const onSignup = vi.fn().mockRejectedValue(
      Object.assign(new Error('Username is already taken.'), { status: 400 }),
    );
    const { user } = renderWithProviders(<Signup onSignup={onSignup} />);
    await user.type(screen.getByLabelText(/family called/i), 'A');
    await user.type(screen.getByLabelText(/sign-in name/i), 'mike');
    await user.type(screen.getByLabelText(/secret word/i), 'pw');
    await user.click(screen.getByRole('button', { name: /found a family/i }));

    expect(await screen.findByText(/already taken/i)).toBeInTheDocument();
  });

  it('shows the sealed empty state on 403', async () => {
    const onSignup = vi.fn().mockRejectedValue(
      Object.assign(new Error('Signup is currently disabled.'), { status: 403 }),
    );
    const { user } = renderWithProviders(<Signup onSignup={onSignup} />);
    await user.type(screen.getByLabelText(/family called/i), 'A');
    await user.type(screen.getByLabelText(/sign-in name/i), 'mike');
    await user.type(screen.getByLabelText(/secret word/i), 'pw');
    await user.click(screen.getByRole('button', { name: /found a family/i }));

    expect(await screen.findByText(/signup is sealed/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to sign in/i })).toBeInTheDocument();
  });

  it('renders a link back to /login', () => {
    renderWithProviders(<Signup onSignup={vi.fn()} />);
    const link = screen.getByRole('link', { name: /have an account\? sign in/i });
    expect(link).toHaveAttribute('href', '/login');
  });
});

describe('Signup → POST /api/auth/signup/', () => {
  it('hits the right endpoint and body when wired through the API', async () => {
    const spy = spyHandler('post', /\/api\/auth\/signup\/$/, {
      token: 'abc',
      user: { id: 1, username: 'mike', role: 'parent' },
      family: { id: 1, name: 'The Sageb Family' },
    });
    server.use(spy.handler);

    // Use a thin onSignup that mimics AuthProvider.signup → POSTs through fetch.
    const onSignup = async (payload) => {
      const res = await fetch('/api/auth/signup/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return res.json();
    };

    const { user } = renderWithProviders(<Signup onSignup={onSignup} />);
    await user.type(screen.getByLabelText(/family called/i), 'A');
    await user.type(screen.getByLabelText(/sign-in name/i), 'mike');
    await user.type(screen.getByLabelText(/secret word/i), 'ApbBy1!Strong');
    await user.click(screen.getByRole('button', { name: /found a family/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      username: 'mike',
      password: 'ApbBy1!Strong',
      family_name: 'A',
    });
  });
});
