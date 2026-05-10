import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
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


/* ── Family tab — co-parent management ─────────────────────────── */

describe('Manage — Family tab', () => {
  it('lists co-parents and renders the requesting parent last with a (you) tag', async () => {
    const me = buildParent({ id: 1, username: 'me', display_name: 'Me' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(me)),
      http.get('*/api/parents/', () =>
        HttpResponse.json([
          { id: 1, username: 'me', display_name: 'Me', role: 'parent', is_active: true, is_primary: true },
          { id: 2, username: 'co', display_name: 'Coparent', role: 'parent', is_active: true, is_primary: false },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    expect(await screen.findByText('Coparent')).toBeInTheDocument();
    expect(screen.getByText(/\(you\)/)).toBeInTheDocument();
    expect(screen.getByText(/founder/i)).toBeInTheDocument();
  });

  it("self-row hides the Edit button so own-profile flows route through /settings", async () => {
    const me = buildParent({ id: 1, username: 'me', display_name: 'Me' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(me)),
      http.get('*/api/parents/', () =>
        HttpResponse.json([
          { id: 1, username: 'me', display_name: 'Me', role: 'parent', is_active: true },
          { id: 2, username: 'co', display_name: 'Coparent', role: 'parent', is_active: true },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    await screen.findByText('Coparent');
    // Exactly one Edit button (for the co-parent), not two.
    const editButtons = screen.getAllByRole('button', { name: /^edit$/i });
    expect(editButtons).toHaveLength(1);
    expect(screen.getByText(/edit your profile in settings/i)).toBeInTheDocument();
  });

  it('Add co-parent posts to /api/parents/ with the typed values', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ id: 1 }))),
    );
    const list = spyHandler('get', /\/api\/parents\/?$/, []);
    server.use(list.handler);
    const create = spyHandler('post', /\/api\/parents\/?$/, {
      id: 2, username: 'newp', role: 'parent',
    });
    server.use(create.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    await user.click(await screen.findByRole('button', { name: /add co-parent/i }));

    const sheet = await screen.findByRole('dialog', { name: /add co-parent/i });
    await user.type(within(sheet).getByLabelText(/sign-in name/i), 'newp');
    await user.type(within(sheet).getByLabelText(/display name/i), 'New Parent');
    await user.type(within(sheet).getByLabelText(/^password$/i), 'ApbBy1!Strong');
    await user.click(within(sheet).getByRole('button', { name: /add co-parent/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({
      username: 'newp',
      display_name: 'New Parent',
      password: 'ApbBy1!Strong',
    });
    await waitFor(() => expect(list.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('reset password for a co-parent posts to /api/parents/<id>/reset-password/', async () => {
    const me = buildParent({ id: 1, username: 'me' });
    const co = { id: 2, username: 'co', display_name: 'Co', role: 'parent', is_active: true };
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(me)),
      http.get('*/api/parents/', () => HttpResponse.json([me, co])),
    );
    const reset = spyHandler('post', /\/api\/parents\/2\/reset-password\/?$/, null, 204);
    server.use(reset.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));
    const editSheet = await screen.findByRole('dialog', { name: /edit co/i });
    await user.click(within(editSheet).getByRole('button', { name: /reset password/i }));
    const resetSheet = await screen.findByRole('dialog', { name: /reset password for/i });
    await user.type(within(resetSheet).getByLabelText(/^new password$/i), 'ApbBy1!Strong');
    await user.type(within(resetSheet).getByLabelText(/^confirm new password$/i), 'ApbBy1!Strong');
    await user.click(within(resetSheet).getByRole('button', { name: /reset password/i }));

    await waitFor(() => expect(reset.calls).toHaveLength(1));
    expect(reset.calls[0].body).toMatchObject({ password: 'ApbBy1!Strong' });
    expect(reset.calls[0].url).toMatch(/\/api\/parents\/2\/reset-password\/?$/);
  });

  it('hard-delete requires the type-to-confirm phrase before firing', async () => {
    const me = buildParent({ id: 1, username: 'me' });
    const co = { id: 2, username: 'co', display_name: 'Co', role: 'parent', is_active: true };
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(me)),
      http.get('*/api/parents/', () => HttpResponse.json([me, co])),
    );
    const del = spyHandler('delete', /\/api\/parents\/2\/?$/, null, 204);
    server.use(del.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));
    await user.click(await screen.findByRole('button', { name: /delete account/i }));

    // The dialog button is disabled until "delete co" is typed.
    const sheet = await screen.findByRole('dialog', { name: /delete co's account/i });
    const confirmBtn = await screen.findAllByRole('button', { name: /delete account/i });
    // The sheet's "Delete account" button is disabled.
    const sheetConfirm = confirmBtn.find((b) => sheet.contains(b));
    expect(sheetConfirm).toBeDisabled();

    // Type wrong phrase — still disabled.
    const input = screen.getByLabelText(/type to confirm/i);
    await user.type(input, 'wrong');
    expect(sheetConfirm).toBeDisabled();
    expect(del.calls).toHaveLength(0);

    // Clear and type the right phrase.
    await user.clear(input);
    await user.type(input, 'delete co');
    expect(sheetConfirm).not.toBeDisabled();
    await user.click(sheetConfirm);
    await waitFor(() => expect(del.calls).toHaveLength(1));
    expect(del.calls[0].url).toMatch(/\/api\/parents\/2\/?$/);
  });

  it('deactivate goes through ConfirmDialog before firing', async () => {
    const me = buildParent({ id: 1, username: 'me' });
    const co = { id: 2, username: 'co', display_name: 'Co', role: 'parent', is_active: true };
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(me)),
      http.get('*/api/parents/', () => HttpResponse.json([me, co])),
    );
    const deactivate = spyHandler('post', /\/api\/parents\/2\/deactivate\/?$/, {});
    server.use(deactivate.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^Family$/ }));
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));

    expect(deactivate.calls).toHaveLength(0);
    // The Edit modal shows a Deactivate trigger; clicking it opens ConfirmDialog.
    const sheet = await screen.findByRole('dialog', { name: /edit co/i });
    const trigger = within(sheet).getByRole('button', { name: /^deactivate$/i });
    await user.click(trigger);
    expect(deactivate.calls).toHaveLength(0);
    // The alertdialog confirm button fires the request.
    const dialog = await screen.findByRole('alertdialog', { name: /deactivate co/i });
    await user.click(within(dialog).getByRole('button', { name: /^deactivate$/i }));
    await waitFor(() => expect(deactivate.calls).toHaveLength(1));
  });
});

/* ── Children tab — extended action trio ───────────────────────── */

describe('Manage — Children action trio', () => {
  it('shows an Inactive chip on inactive children when "Show inactive" is toggled', async () => {
    const parent = buildParent();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () =>
        HttpResponse.json([
          { id: 7, username: 'old', display_name: 'Old Kid', role: 'child', is_active: false, hourly_rate: '8.00' },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    // Inactive child is hidden by default.
    await screen.findByText(/no children yet/i);
    expect(screen.queryByText('Old Kid')).toBeNull();
    // Toggle to show inactive.
    await user.click(screen.getByRole('button', { name: /show inactive/i }));
    expect(screen.getByText('Old Kid')).toBeInTheDocument();
    expect(screen.getByText(/^inactive$/i)).toBeInTheDocument();
  });

  it('hard-delete a child requires the type-to-confirm phrase', async () => {
    const parent = buildParent();
    const child = buildUser({ id: 7, role: 'child', display_name: 'Abby', username: 'abby' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([child])),
    );
    const del = spyHandler('delete', /\/api\/children\/7\/?$/, null);
    server.use(del.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));
    const editSheet = await screen.findByRole('dialog', { name: /edit abby/i });
    await user.click(within(editSheet).getByRole('button', { name: /delete account/i }));

    const confirmSheet = await screen.findByRole('dialog', { name: /delete abby's account/i });
    const confirmBtn = within(confirmSheet).getByRole('button', { name: /delete account/i });
    expect(confirmBtn).toBeDisabled();

    await user.type(within(confirmSheet).getByLabelText(/type to confirm/i), 'delete abby');
    expect(confirmBtn).not.toBeDisabled();
    await user.click(confirmBtn);
    await waitFor(() => expect(del.calls).toHaveLength(1));
  });

  it('reset password for a child posts to /api/children/<id>/reset-password/', async () => {
    const parent = buildParent();
    const child = buildUser({ id: 7, role: 'child', display_name: 'Abby' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([child])),
    );
    const reset = spyHandler('post', /\/api\/children\/7\/reset-password\/?$/, null, 204);
    server.use(reset.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));
    const editSheet = await screen.findByRole('dialog', { name: /edit abby/i });
    await user.click(within(editSheet).getByRole('button', { name: /reset password/i }));
    const resetSheet = await screen.findByRole('dialog', { name: /reset password for/i });
    await user.type(within(resetSheet).getByLabelText(/^new password$/i), 'ApbBy1!Strong');
    await user.type(within(resetSheet).getByLabelText(/^confirm new password$/i), 'ApbBy1!Strong');
    await user.click(within(resetSheet).getByRole('button', { name: /reset password/i }));
    await waitFor(() => expect(reset.calls).toHaveLength(1));
    expect(reset.calls[0].body).toMatchObject({ password: 'ApbBy1!Strong' });
  });
});

/* ── ResetPasswordModal — client-side mismatch guard ──────────── */

describe('ResetPasswordModal', () => {
  it('blocks submit and surfaces an error when the two passwords differ', async () => {
    const parent = buildParent();
    const child = buildUser({ id: 7, role: 'child', display_name: 'Abby' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/children/', () => HttpResponse.json([child])),
    );
    const reset = spyHandler('post', /\/api\/children\/7\/reset-password\/?$/, null);
    server.use(reset.handler);

    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^edit$/i }));
    const editSheet = await screen.findByRole('dialog', { name: /edit abby/i });
    await user.click(within(editSheet).getByRole('button', { name: /reset password/i }));

    const sheet = await screen.findByRole('dialog', { name: /reset password for/i });
    await user.type(within(sheet).getByLabelText(/^new password$/i), 'AaaaA1!Strong');
    await user.type(within(sheet).getByLabelText(/^confirm new password$/i), 'BbbbB2!Different');
    await user.click(within(sheet).getByRole('button', { name: /reset password/i }));

    expect(within(sheet).getByText(/passwords do not match/i)).toBeInTheDocument();
    // No backend round-trip on the mismatch path.
    expect(reset.calls).toHaveLength(0);
  });
});

/* ── Admin tab — staff only ────────────────────────────────────── */

describe('Manage — Admin tab', () => {
  it('hides the Admin tab when /api/admin/families/ returns 403', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/admin/families/', () => new HttpResponse(null, { status: 403 })),
    );
    renderPage();
    await screen.findByText(/children/i);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole('button', { name: /^Admin$/ })).toBeNull();
  });

  it('shows the Admin tab when /api/admin/families/ returns 200 and posts a new family', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/admin/families/', () => HttpResponse.json({ ok: true })),
    );
    const create = spyHandler('post', /\/api\/admin\/families\/?$/, {
      token: 't',
      user: { username: 'founder' },
      family: { name: 'New House' },
    }, 201);
    server.use(create.handler);

    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Admin$/ })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /^Admin$/ }));
    await user.type(await screen.findByLabelText(/family name/i), 'New House');
    await user.type(screen.getByLabelText(/sign-in name/i), 'founder');
    await user.type(screen.getByLabelText(/^password$/i), 'ApbBy1!Strong');
    await user.click(screen.getByRole('button', { name: /create family/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({
      family_name: 'New House',
      username: 'founder',
      password: 'ApbBy1!Strong',
    });
    expect(await screen.findByText(/Created.*New House/i)).toBeInTheDocument();
  });
});
