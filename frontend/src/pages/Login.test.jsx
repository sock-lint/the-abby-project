import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Login from './Login.jsx';
import { server } from '../test/server.js';

afterEach(() => {
  window.history.replaceState({}, '', '/');
});

describe('Login', () => {
  it('renders the form fields', () => {
    server.use(
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    render(<Login onLogin={() => {}} />);
    expect(screen.getByLabelText(/name in the ledger/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/secret word/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enter/i })).toBeInTheDocument();
  });

  it('calls onLogin with entered credentials', async () => {
    server.use(
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    const onLogin = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<Login onLogin={onLogin} />);
    await user.type(screen.getByLabelText(/name in the ledger/i), 'abby');
    await user.type(screen.getByLabelText(/secret word/i), 'pw');
    await user.click(screen.getByRole('button', { name: /enter/i }));
    expect(onLogin).toHaveBeenCalledWith('abby', 'pw');
  });

  it('displays an error when login fails', async () => {
    server.use(
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    const onLogin = vi.fn().mockRejectedValue(new Error('bad password'));
    const user = userEvent.setup();
    render(<Login onLogin={onLogin} />);
    await user.type(screen.getByLabelText(/name in the ledger/i), 'a');
    await user.type(screen.getByLabelText(/secret word/i), 'b');
    await user.click(screen.getByRole('button', { name: /enter/i }));
    expect(await screen.findByText(/bad password/i)).toBeInTheDocument();
  });

  it('shows the Google button when the backend advertises OAuth', async () => {
    server.use(
      http.get('*/api/auth/google/login/', () =>
        HttpResponse.json({ authorization_url: 'https://accounts.google.com/…' }),
      ),
    );
    render(<Login onLogin={() => {}} />);
    await waitFor(() => expect(screen.getByText(/sign in with google/i)).toBeInTheDocument());
  });

  it('redirects to the Google OAuth URL when clicked', async () => {
    const url = 'https://accounts.google.com/auth';
    server.use(
      http.get('*/api/auth/google/login/', () =>
        HttpResponse.json({ authorization_url: url }),
      ),
    );
    const user = userEvent.setup();
    render(<Login onLogin={() => {}} />);
    await waitFor(() => expect(screen.getByText(/sign in with google/i)).toBeInTheDocument());
    // Stub window.location via defineProperty so assignment doesn't actually
    // navigate jsdom.
    const hrefSetter = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new Proxy(window.location, {
        set(target, prop, value) {
          if (prop === 'href') { hrefSetter(value); return true; }
          target[prop] = value; return true;
        },
      }),
    });
    await user.click(screen.getByRole('button', { name: /sign in with google/i }));
    await waitFor(() => expect(hrefSetter).toHaveBeenCalledWith(url));
  });

  it('surfaces the ?google_error=no_account banner', () => {
    server.use(
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    window.history.pushState({}, '', '/?google_error=no_account');
    render(<Login onLogin={() => {}} />);
    expect(screen.getByText(/no linked google account/i)).toBeInTheDocument();
  });

  it('surfaces the ?google_error=inactive banner', () => {
    server.use(
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    window.history.pushState({}, '', '/?google_error=inactive');
    render(<Login onLogin={() => {}} />);
    expect(screen.getByText(/account is inactive/i)).toBeInTheDocument();
  });

  it('hides the Google button if auth/google/login fails', async () => {
    server.use(
      http.get('*/api/auth/google/login/', () =>
        HttpResponse.json({ error: 'nope' }, { status: 500 }),
      ),
    );
    render(<Login onLogin={() => {}} />);
    // Wait a tick; the button must never appear.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/sign in with google/i)).toBeNull();
  });

  it('handles google login URL fetch error', async () => {
    server.use(
      http.get('*/api/auth/google/login/', () =>
        HttpResponse.json({ authorization_url: 'x' }),
      ),
    );
    const user = userEvent.setup();
    render(<Login onLogin={() => {}} />);
    await waitFor(() => expect(screen.getByText(/sign in with google/i)).toBeInTheDocument());
    // Second call (on click) fails:
    server.use(
      http.get('*/api/auth/google/login/', () =>
        HttpResponse.json({ error: 'x' }, { status: 500 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: /sign in with google/i }));
    expect(await screen.findByText(/could not start google sign-in/i)).toBeInTheDocument();
  });
});
