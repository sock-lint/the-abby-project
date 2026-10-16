import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from './test/server';
import { AuthProvider, useAuth } from './hooks/useApi';
import { applyTheme, themes } from './themes';
import { buildUser } from './test/factories';
import App from './App';

vi.mock('./pages/__design', () => ({ default: function Preview() {
  return <button onClick={() => applyTheme('vigil')}>Choose local preview</button>;
} }));

function AccountState() {
  const { user } = useAuth();
  return <output>{user ? `Account loaded: ${user.theme}` : 'Account pending'}</output>;
}

describe('design route isolation', () => {
  afterEach(() => { window.history.replaceState({}, '', '/'); applyTheme('hyrule'); });
  it('keeps the local preview theme and omits celebration reads after delayed authentication', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const birthday = vi.fn(() => new HttpResponse(null, { status: 204 }));
    const reward = vi.fn(() => new HttpResponse(null, { status: 204 }));
    server.use(
      http.get('*/api/auth/me/', async () => { await pending; return HttpResponse.json(buildUser({ theme: 'sunlit' })); }),
      http.get('*/api/chronicle/pending-celebration/', birthday),
      http.get('*/api/notifications/pending-celebration/', reward),
    );
    window.history.replaceState({}, '', '/__design');
    render(<AuthProvider><App /><AccountState /></AuthProvider>);
    fireEvent.click(await screen.findByRole('button', { name: 'Choose local preview' }));
    expect(document.documentElement.style.getPropertyValue('--color-ink-page')).toBe(themes.vigil.page);
    await act(async () => finish());
    await screen.findByText('Account loaded: sunlit');
    expect(document.documentElement.style.getPropertyValue('--color-ink-page')).toBe(themes.vigil.page);
    expect(birthday).not.toHaveBeenCalled();
    expect(reward).not.toHaveBeenCalled();
  });
});
