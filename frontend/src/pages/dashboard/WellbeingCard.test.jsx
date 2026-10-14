import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import WellbeingCard from './WellbeingCard.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const TODAY = new Date().toISOString().slice(0, 10);

const FRESH_TODAY = {
  id: 7,
  date: TODAY,
  is_today: true,
  affirmation: {
    slug: 'rest-is-progress',
    text: 'Rest is part of the work, not a break from it.',
    tone: 'calm',
  },
  gratitude_lines: [],
  gratitude_paid: false,
  max_lines: 3,
  max_line_chars: 200,
  coin_reward: 2,
};

function renderCard(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <WellbeingCard />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('WellbeingCard', () => {
  it('invites one daily note and prevents empty saves without an error', async () => {
    const user = userEvent.setup();
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, {});
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)), submit.handler,
    ]);
    await screen.findByText(FRESH_TODAY.affirmation.text);
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.getByText(/one short line is enough/i)).toBeInTheDocument();
    expect(screen.queryByText(/0\/3|blanks are fine|three small things/i)).not.toBeInTheDocument();
    const note = screen.getByRole('textbox', { name: "Today's note" });
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    await user.type(note, '   ');
    expect(save).toBeDisabled();
    await user.click(save);
    expect(submit.calls).toHaveLength(0);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('saves a personal thought using the successful response even if a later GET would be empty', async () => {
    const user = userEvent.setup();
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, ({ body }) => ({
      ...FRESH_TODAY, gratitude_lines: body.lines, gratitude_paid: true,
      coin_awarded: 2, freshly_paid: true,
    }));
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)), submit.handler,
    ]);
    const note = await screen.findByRole('textbox', { name: "Today's note" });
    await user.type(note, '  Today was hard, but I tried.  ');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['Today was hard, but I tried.'] });
    expect(await screen.findByText('Saved for today')).toBeInTheDocument();
    expect(note).toHaveValue('Today was hard, but I tried.');
    expect(screen.getByLabelText('Daily note reward')).toHaveTextContent('+2');
    expect(screen.getByRole('button', { name: 'Update' })).toBeEnabled();
    expect(screen.queryByText(/first save today earns/i)).not.toBeInTheDocument();
  });

  it('offers optional ideas without inserting text or submitting anything', async () => {
    const user = userEvent.setup();
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, {});
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)), submit.handler,
    ]);
    const note = await screen.findByRole('textbox', { name: "Today's note" });
    await user.click(screen.getByText('Need an idea? (optional)'));
    await user.click(screen.getByRole('button', { name: 'Something I tried' }));
    expect(note).toHaveAttribute('placeholder', 'Something I tried today…');
    expect(note).toHaveValue('');
    expect(note).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(submit.calls).toHaveLength(0);
    expect(screen.queryByLabelText('Daily note reward')).not.toBeInTheDocument();
    await user.type(note, 'I tried drawing');
    await user.click(screen.getByRole('button', { name: 'Someone I appreciate' }));
    expect(note).toHaveValue('I tried drawing');
  });

  it('preserves all saved lines and edits without claiming another daily reward', async () => {
    const user = userEvent.setup();
    const paid = { ...FRESH_TODAY, gratitude_paid: true, gratitude_lines: ['One', 'Two', 'Three'] };
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, ({ body }) => ({
      ...paid, gratitude_lines: body.lines, freshly_paid: false, coin_awarded: 0,
    }));
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(paid)), submit.handler,
    ]);
    const note = await screen.findByRole('textbox', { name: "Today's note" });
    await waitFor(() => expect(note).toHaveValue('One'));
    expect(screen.getAllByRole('textbox')).toHaveLength(3);
    expect(screen.getByRole('textbox', { name: 'Another thought (optional)' })).toHaveValue('Two');
    expect(screen.getByRole('textbox', { name: 'One more thought (optional)' })).toHaveValue('Three');
    expect(screen.getByText('Saved for today')).toBeInTheDocument();
    await user.clear(note);
    await user.type(note, 'Different thought');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['Different thought', 'Two', 'Three'] });
    expect(await screen.findByText('Saved for today')).toBeInTheDocument();
    expect(screen.queryByLabelText('Daily note reward')).not.toBeInTheDocument();
  });

  it('keeps the draft and offers a retry when saving fails', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
      http.post('*/api/wellbeing/today/gratitude/', async ({ request }) => {
        attempts += 1;
        if (attempts === 1) return HttpResponse.json({ error: 'Could not save. Try again.' }, { status: 503 });
        const body = await request.json();
        return HttpResponse.json({ ...FRESH_TODAY, gratitude_lines: body.lines, freshly_paid: false });
      }),
    ]);
    const note = await screen.findByRole('textbox', { name: "Today's note" });
    await user.type(note, 'Something I want to remember');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save. Try again.');
    expect(note).toHaveValue('Something I want to remember');
    expect(screen.queryByText('Saved for today')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Saved for today')).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it('allows a saved note to retry its unconfirmed daily reward without requiring an edit', async () => {
    const user = userEvent.setup();
    const unpaid = { ...FRESH_TODAY, gratitude_lines: ['Already saved'], gratitude_paid: false };
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, {
      ...unpaid, gratitude_paid: true, freshly_paid: true, coin_awarded: 2,
    });
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(unpaid)), submit.handler,
    ]);
    expect(await screen.findByText('Saved for today')).toBeInTheDocument();
    const update = screen.getByRole('button', { name: 'Update' });
    expect(update).toBeEnabled();
    await user.click(update);
    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['Already saved'] });
    expect(await screen.findByLabelText('Daily note reward')).toHaveTextContent('+2');
    expect(update).toBeEnabled();
  });

  it('renders today’s affirmation text', async () => {
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );
  });

  it('Save POSTs the typed gratitude lines and shows a coin chip on first-of-day pay', async () => {
    const user = userEvent.setup();
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, ({ body }) => ({
      ...FRESH_TODAY,
      gratitude_lines: body?.lines || [],
      gratitude_paid: true,
      coin_awarded: 2,
      freshly_paid: true,
    }));
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
      submit.handler,
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );

    await user.click(screen.getByRole('button', { name: /add more thoughts/i }));
    const inputs = screen.getAllByRole('textbox');
    expect(inputs).toHaveLength(3);
    await user.type(inputs[0], 'warm bread');
    await user.type(inputs[2], 'a quiet morning');
    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['warm bread', 'a quiet morning'] });
    // Coin flash chip appears (role=status separates it from the
    // "first save today earns +2" hint that's always visible).
    await waitFor(() =>
      expect(screen.getByLabelText('Daily note reward')).toHaveTextContent(/\+2/),
    );
  });

  it('disables Save when no lines are written', async () => {
    const user = userEvent.setup();
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(FRESH_TODAY)),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/Rest is part of the work/)).toBeInTheDocument(),
    );
    const save = screen.getByRole('button', { name: /save/i });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows Update label and skips coin chip when today’s row already paid', async () => {
    const paid = { ...FRESH_TODAY, gratitude_paid: true, gratitude_lines: ['previous note'] };
    renderCard([
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(paid)),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument(),
    );
    // No "first save earns +2" hint when already paid.
    expect(screen.queryByText(/first save today earns/i)).toBeNull();
  });
});
