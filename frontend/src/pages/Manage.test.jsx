import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Manage from './Manage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';
import { spyHandler } from '../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Manage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Manage', () => {
  it('renders the children tab by default', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () =>
        HttpResponse.json([buildUser({ id: 3, display_name: 'Abby' })]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/children/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Abby')).toBeInTheDocument());
  });

  it('switches to the templates tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/templates/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /templates/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /templates/i }));
    await waitFor(() =>
      expect(screen.getAllByText((t) => /template/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('switches to the codex tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /codex/i }));
    await waitFor(() =>
      expect(screen.getAllByText((t) => /codex/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('switches to the guide tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/lorebook/', () =>
        HttpResponse.json({
          counts: { unlocked: 1, total: 1 },
          entries: [
            {
              slug: 'study',
              title: 'Study',
              icon: '📚',
              chapter: 'daily_life',
              summary: 'Homework is practice, not paid work.',
              kid_voice: 'Study earns mastery.',
              mechanics: ['Homework pays no money and no Coins.'],
              parent_knobs: {},
              economy: {
                money: false,
                coins: false,
                xp: true,
                drops: true,
                quest_progress: true,
                streak_credit: true,
              },
              unlocked: true,
            },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /guide/i }));
    expect(await screen.findByRole('heading', { name: /economy diagram/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /study/i })).toBeInTheDocument();
  });
});

describe('Manage — create child flow', () => {
  it('opens the BottomSheet when "New child" is clicked', async () => {
    const parent = buildParent();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([])),
    );

    const user = userEvent.setup();
    renderPage();

    const newChildBtn = await screen.findByRole('button', { name: /new child/i });
    await user.click(newChildBtn);

    // BottomSheet portals to body, so query off document not container.
    expect(
      await screen.findByRole('dialog', { name: /new child/i }),
    ).toBeInTheDocument();
    // Form fields render.
    expect(screen.getByLabelText(/sign-in name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/secret word/i)).toBeInTheDocument();
  });

  it('posts to /api/children/ with the typed values, then refetches', async () => {
    const parent = buildParent();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
    );

    const childrenList = spyHandler('get', /\/api\/children\/?$/, []);
    server.use(childrenList.handler);

    const create = spyHandler('post', /\/api\/children\/?$/, {
      id: 99, username: 'newkid', role: 'child',
    });
    server.use(create.handler);

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /new child/i }));

    await user.type(await screen.findByLabelText(/sign-in name/i), 'newkid');
    await user.type(screen.getByLabelText(/display name/i), 'New Kid');
    await user.type(screen.getByLabelText(/secret word/i), 'ApbBy1!Strong');
    await user.click(screen.getByRole('button', { name: /create child/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({
      username: 'newkid',
      password: 'ApbBy1!Strong',
      display_name: 'New Kid',
      hourly_rate: '8.00',
    });

    // After successful create the children list refetches — count >= 2 (mount + reload).
    await waitFor(() => expect(childrenList.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('surfaces a 400 error inline without closing the modal', async () => {
    const parent = buildParent();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.post('*/api/children/', () =>
        HttpResponse.json({ username: ['already taken'] }, { status: 400 }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /new child/i }));
    await user.type(await screen.findByLabelText(/sign-in name/i), 'taken');
    await user.type(screen.getByLabelText(/secret word/i), 'pw');
    await user.click(screen.getByRole('button', { name: /create child/i }));

    expect(await screen.findByText(/already taken/i)).toBeInTheDocument();
    // Modal stayed open.
    expect(screen.getByRole('dialog', { name: /new child/i })).toBeInTheDocument();
  });
});


describe('Manage — child DOB + grade_entry_year', () => {
  it('saving patches /api/children/{id}/ with both fields', async () => {
    const parent = buildParent();
    const child = buildUser({ id: 7, role: 'child', display_name: 'Abby' });

    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([child])),
    );

    const spy = spyHandler('patch', /\/api\/children\/7\/?$/, {});
    server.use(spy.handler);

    const user = userEvent.setup();
    renderPage();

    // Click the Edit button on Abby's card
    const editBtn = await screen.findByRole('button', { name: /edit/i });
    await user.click(editBtn);

    // Fill in the date-of-birth field
    const dobInput = await screen.findByLabelText(/date of birth/i);
    await user.clear(dobInput);
    await user.type(dobInput, '2011-09-22');

    // Select a grade entry year
    const gradeSelect = await screen.findByLabelText(/grade entry year/i);
    await user.selectOptions(gradeSelect, '2025');

    // Submit the form
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      date_of_birth: '2011-09-22',
      grade_entry_year: 2025,
    });
    expect(spy.calls[0].url).toMatch(/\/api\/children\/7\/?$/);
  });

  it('hides the Test tab when /api/dev/ping/ returns 403', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/dev/ping/', () => new HttpResponse(null, { status: 403 })),
    );
    renderPage();
    await screen.findByText(/children/i);
    // Wait a tick so the ping resolves either way.
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole('button', { name: /^Test$/ })).toBeNull();
  });

  it('shows the Test tab when /api/dev/ping/ returns 200', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/dev/ping/', () => HttpResponse.json({ enabled: true, user: 'dad' })),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Test$/ })).toBeInTheDocument();
    });
  });
});
