import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CoinAdjustModal from './CoinAdjustModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const KIDS = [
  { id: 11, username: 'abby', display_name: 'Abby' },
  { id: 12, username: 'sam', display_name: 'Sam' },
];

function useKidsHandler() {
  return http.get('*/api/children/', () => HttpResponse.json(KIDS));
}

describe('CoinAdjustModal', () => {
  it('renders a kid picker populated from /api/children/', async () => {
    server.use(useKidsHandler());
    render(<CoinAdjustModal onClose={vi.fn()} onSaved={vi.fn()} />);

    const select = await screen.findByRole('combobox', { name: /kid/i });
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(screen.getByRole('option', { name: 'Abby' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Sam' })).toBeInTheDocument();
  });

  it('posts the chosen numeric user_id to /api/coins/adjust/', async () => {
    const user = userEvent.setup();
    const adjust = spyHandler('post', /\/api\/coins\/adjust\/$/, { ok: true });
    const onSaved = vi.fn();
    server.use(useKidsHandler(), adjust.handler);
    render(<CoinAdjustModal onClose={vi.fn()} onSaved={onSaved} />);

    const select = await screen.findByRole('combobox', { name: /kid/i });
    await waitFor(() => expect(select).not.toBeDisabled());
    await user.selectOptions(select, '12');

    const amount = screen.getByRole('spinbutton');
    await user.type(amount, '25');

    await user.click(screen.getByRole('button', { name: /^adjust$/i }));

    await waitFor(() => expect(adjust.calls).toHaveLength(1));
    expect(adjust.calls[0].body).toEqual({
      user_id: 12,
      amount: 25,
      description: '',
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it('surfaces server error', async () => {
    const user = userEvent.setup();
    server.use(
      useKidsHandler(),
      http.post('*/api/coins/adjust/', () =>
        HttpResponse.json({ error: 'bad' }, { status: 400 }),
      ),
    );
    render(<CoinAdjustModal onClose={vi.fn()} onSaved={vi.fn()} />);

    const select = await screen.findByRole('combobox', { name: /kid/i });
    await waitFor(() => expect(select).not.toBeDisabled());
    await user.selectOptions(select, '11');

    const amount = screen.getByRole('spinbutton');
    await user.type(amount, '10');

    await user.click(screen.getByRole('button', { name: /^adjust$/i }));
    expect(await screen.findByText(/bad/i)).toBeInTheDocument();
  });
});
