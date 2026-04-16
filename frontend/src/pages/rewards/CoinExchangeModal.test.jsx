import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CoinExchangeModal from './CoinExchangeModal.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('CoinExchangeModal', () => {
  it('renders rate and balance', async () => {
    server.use(
      http.get('*/api/balance/', () => HttpResponse.json({ balance: 20 })),
    );
    render(<CoinExchangeModal exchangeRate={10} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/\$1\.00 = 10 coins/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('$20.00')).toBeInTheDocument());
  });

  it('submits exchange request', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.get('*/api/balance/', () => HttpResponse.json({ balance: 50 })),
      http.post('*/api/coins/exchange/', () => HttpResponse.json({})),
    );
    render(<CoinExchangeModal exchangeRate={10} onClose={vi.fn()} onSaved={onSaved} />);
    await waitFor(() => expect(screen.getByText('$50.00')).toBeInTheDocument());
    const input = screen.getByRole('spinbutton');
    await user.type(input, '5');
    await user.click(screen.getByRole('button', { name: /request exchange/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
