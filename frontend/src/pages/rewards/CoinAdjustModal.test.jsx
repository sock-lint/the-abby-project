import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CoinAdjustModal from './CoinAdjustModal.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('CoinAdjustModal', () => {
  it('submits adjustment', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(http.post('*/api/coins/adjust/', () => HttpResponse.json({})));
    render(<CoinAdjustModal onClose={vi.fn()} onSaved={onSaved} />);
    const fields = screen.getAllByRole('spinbutton');
    await user.type(fields[0], '3');
    await user.type(fields[1], '10');
    await user.click(screen.getByRole('button', { name: /^adjust$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('surfaces server error', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('*/api/coins/adjust/', () =>
        HttpResponse.json({ error: 'bad' }, { status: 400 }),
      ),
    );
    render(<CoinAdjustModal onClose={vi.fn()} onSaved={vi.fn()} />);
    const fields = screen.getAllByRole('spinbutton');
    await user.type(fields[0], '3');
    await user.type(fields[1], '10');
    await user.click(screen.getByRole('button', { name: /^adjust$/i }));
    expect(await screen.findByText(/bad/i)).toBeInTheDocument();
  });
});
