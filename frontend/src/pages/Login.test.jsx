import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Login from './Login.jsx';
import { server } from '../test/server.js';
import { GOOGLE_STATE, GOOGLE_URL, interceptGoogleNavigation } from '../test/googleAuthorization';
import { setToken } from '../api/client';

afterEach(() => {
  window.history.replaceState({}, '', '/');
  vi.unstubAllEnvs();
});

const renderLogin = (props) =>
  render(
    <MemoryRouter>
      <Login onLogin={props?.onLogin || (() => {})} sessionError={props?.sessionError} />
    </MemoryRouter>,
  );

describe('Login', () => {
  it('explains an account-switch cleanup failure while keeping sign-in available', () => {
    renderLogin({ sessionError: 'Could not stop notifications on this device. Reconnect and try again.' });
    expect(screen.getByRole('alert')).toHaveTextContent(/could not stop notifications/i);
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled();
  });
  it('renders the form fields', () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    renderLogin();
    expect(screen.getByLabelText(/^username$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
  });

  it('shows the "Create a family" link by default', () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    renderLogin();
    const link = screen.getByRole('link', { name: /create a family/i });
    expect(link).toHaveAttribute('href', '/signup');
  });

  it('hides the "Create a family" link when VITE_ALLOW_SIGNUP is false', () => {
    vi.stubEnv('VITE_ALLOW_SIGNUP', 'false');
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    renderLogin();
    expect(screen.queryByRole('link', { name: /create a family/i })).toBeNull();
  });

  it('calls onLogin with entered credentials', async () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    const onLogin = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    renderLogin({ onLogin });
    await user.type(screen.getByLabelText(/^username$/i), 'abby');
    await user.type(screen.getByLabelText(/^password$/i), 'pw');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(onLogin).toHaveBeenCalledWith('abby', 'pw');
  });

  it('displays an error when login fails', async () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    const onLogin = vi.fn().mockRejectedValue(new Error('bad password'));
    const user = userEvent.setup();
    renderLogin({ onLogin });
    await user.type(screen.getByLabelText(/^username$/i), 'a');
    await user.type(screen.getByLabelText(/^password$/i), 'b');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(await screen.findByText(/bad password/i)).toBeInTheDocument();
  });

  it('shows the Google button when the backend advertises OAuth', async () => {
    server.use(
      http.get('*/api/auth/google/config/', () =>
        HttpResponse.json({ configured: true }),
      ),
    );
    renderLogin();
    await waitFor(() => expect(screen.getByText(/sign in with google/i)).toBeInTheDocument());
  });

  it('starts one proof-bound Google request on a double click and navigates only after success', async () => {
    const starts = [];
    let finish;
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({ configured: true })),
      http.get('*/api/auth/google/login/', ({ request }) => {
        starts.push(request);
        return new Promise(resolve => { finish = () => resolve(HttpResponse.json({ authorization_url: GOOGLE_URL, state: GOOGLE_STATE, expires_in: 600 })); });
      }),
    );
    const user = userEvent.setup();
    const navigation = interceptGoogleNavigation();
    try {
      renderLogin();
      const button = await screen.findByRole('button', { name: /sign in with google/i });
      await user.dblClick(button);
      await waitFor(() => expect(starts).toHaveLength(1));
      expect(button).toBeDisabled();
      expect(new URL(starts[0].url).searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(starts[0].headers.get('authorization')).toBeNull();
      finish();
      await waitFor(() => expect(navigation.destinations).toEqual([GOOGLE_URL]));
      expect(button).toBeDisabled();
      const event = new Event('pageshow');
      Object.defineProperty(event, 'persisted', { value: true });
      window.dispatchEvent(event);
      await waitFor(() => expect(button).toBeEnabled());
      expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull();
    } finally { navigation.restore(); }
  });

  it('does not navigate a delayed Google start after another account signs in', async () => {
    const requests = [];
    let finish;
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({ configured: true })),
      http.get('*/api/auth/google/login/', () => {
        requests.push(true);
        return new Promise(resolve => { finish = () => resolve(HttpResponse.json({ authorization_url: GOOGLE_URL, state: GOOGLE_STATE, expires_in: 600 })); });
      }),
    );
    const navigation = interceptGoogleNavigation();
    try {
      renderLogin();
      await userEvent.click(await screen.findByRole('button', { name: /sign in with google/i }));
      await waitFor(() => expect(requests).toHaveLength(1));
      setToken('another-account');
      finish();
      await waitFor(() => expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull());
      expect(navigation.destinations).toEqual([]);
    } finally { navigation.restore(); }
  });

  it('surfaces the ?google_error=no_account banner', () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    window.history.pushState({}, '', '/?google_error=no_account');
    renderLogin();
    expect(screen.getByText(/no linked google account/i)).toBeInTheDocument();
  });

  it('surfaces the ?google_error=inactive banner', () => {
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({})),
    );
    window.history.pushState({}, '', '/?google_error=inactive');
    renderLogin();
    expect(screen.getByText(/account is inactive/i)).toBeInTheDocument();
  });

  it('hides the Google button if auth/google/login fails', async () => {
    server.use(
      http.get('*/api/auth/google/config/', () =>
        HttpResponse.json({ error: 'nope' }, { status: 500 }),
      ),
    );
    renderLogin();
    // Wait a tick; the button must never appear.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/sign in with google/i)).toBeNull();
  });

  it('shows a failed start and retries with a fresh proof after an explicit click', async () => {
    const starts = [];
    server.use(
      http.get('*/api/auth/google/config/', () => HttpResponse.json({ configured: true })),
      http.get('*/api/auth/google/login/', ({ request }) => {
        starts.push(request);
        return HttpResponse.json({ error: 'unavailable' }, { status: 503 });
      }),
    );
    const user = userEvent.setup();
    renderLogin();
    const button = await screen.findByRole('button', { name: /sign in with google/i });
    await user.click(button);
    expect(await screen.findByText(/could not start google sign-in/i)).toBeInTheDocument();
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() => expect(starts).toHaveLength(2));
    expect(new URL(starts[0].url).searchParams.get('code_challenge')).not.toBe(new URL(starts[1].url).searchParams.get('code_challenge'));
  });
});
