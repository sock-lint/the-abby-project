import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Trials from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser, buildParent } from '../../test/factories.js';
import { setToken } from '../../api/client.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const defBoss = (overrides = {}) => ({
  id: 1, name: 'Dragon Slayer', description: 'slay the dragon',
  icon: '🐲', sprite_key: '', quest_type: 'boss',
  quest_type_display: 'Boss Fight', target_value: 100,
  duration_days: 7, coin_reward: 50, xp_reward: 100, required_badge: null,
  ...overrides,
});

function renderTrials(initialEntries = ['/quests?tab=trials']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>
        <Trials />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  try { window.localStorage.clear(); } catch { /* ignore */ }
  setToken('challenges-test-session');
});

describe('Challenges (illuminated codex)', () => {
  it('renders the IncipitBand hero with the script kicker', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderTrials();
    expect(await screen.findByRole('heading', { level: 1, name: /^Challenges$/ }))
      .toBeInTheDocument();
    expect(screen.getByText(/Complete tasks to make progress/i))
      .toBeInTheDocument();
  });

  it('lists available challenges and starts one when Begin is tapped', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/quests/available/', () =>
        HttpResponse.json([defBoss({ id: 7, name: 'Slay the Beast' })]),
      ),
    );
    const startSpy = spyHandler('post', /\/api\/quests\/start\/$/, { ok: true });
    server.use(startSpy.handler);

    renderTrials();

    const beginBtn = await screen.findByRole('button', { name: /^Start challenge$/ });
    const user = userEvent.setup();
    await user.click(beginBtn);

    await waitFor(() => expect(startSpy.calls).toHaveLength(1));
    expect(startSpy.calls[0].body).toMatchObject({ definition_id: 7 });
  });

  it('propagates the ?scroll= deep-link param through to startQuest', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/quests/available/', () =>
        HttpResponse.json([defBoss({ id: 9, name: 'Beast Hunt' })]),
      ),
    );
    const startSpy = spyHandler('post', /\/api\/quests\/start\/$/, { ok: true });
    server.use(startSpy.handler);

    renderTrials(['/quests?tab=trials&scroll=42']);

    const beginBtn = await screen.findByRole('button', { name: /^Start challenge$/ });
    const user = userEvent.setup();
    await user.click(beginBtn);

    await waitFor(() => expect(startSpy.calls).toHaveLength(1));
    expect(startSpy.calls[0].body).toEqual({
      definition_id: 9,
      scroll_item_id: '42',
    });
  });

  it('shows the parent Create challenge button when role=parent + has children', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
    );
    renderTrials();
    expect(
      await screen.findByRole('button', { name: /Create challenge/i }),
    ).toBeInTheDocument();
  });

  it('hides Create challenge for child users', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderTrials();
    // Wait for the page to settle, then assert button is absent.
    expect(
      await screen.findByRole('heading', { level: 1, name: /^Challenges$/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Create challenge/i }),
    ).toBeNull();
  });

  it('routes a badge-gated available challenge into the Locked chapter', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/quests/available/', () =>
        HttpResponse.json([
          defBoss({
            id: 1, name: 'Hidden Challenge',
            required_badge: 42, required_badge_name: 'Iron Will',
          }),
        ]),
      ),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    renderTrials();
    const user = userEvent.setup();
    const lockedSpine = await screen.findByRole('tab', { name: /Locked/ });
    await user.click(lockedSpine);
    expect(await screen.findByText(/Hidden Challenge/)).toBeInTheDocument();
    expect(screen.getByText(/Iron Will badge to unlock/i)).toBeInTheDocument();
  });
});
