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

  it('never claims $0.00 while the balance is still loading', async () => {
    let release;
    const gate = new Promise((r) => { release = r; });
    server.use(
      http.get('*/api/balance/', async () => {
        await gate;
        return HttpResponse.json({ balance: 12 });
      }),
    );
    render(<CoinExchangeModal exchangeRate={10} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByText(/checking…/i)).toBeInTheDocument();
    expect(screen.queryByText('$0.00')).toBeNull();

    release();
    await waitFor(() => expect(screen.getByText('$12.00')).toBeInTheDocument());
  });

  it('explains why the request button is disabled', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/balance/', () => HttpResponse.json({ balance: 3.2 })),
    );
    render(<CoinExchangeModal exchangeRate={10} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('$3.20')).toBeInTheDocument());

    await user.type(screen.getByRole('spinbutton'), '9');
    expect(await screen.findByText(/you only have \$3\.20/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /request exchange/i })).toBeDisabled();

    await user.clear(screen.getByRole('spinbutton'));
    await user.type(screen.getByRole('spinbutton'), '0.5');
    expect(await screen.findByText(/minimum is \$1\.00/i)).toBeInTheDocument();
  });

  it('surfaces a failed balance fetch with a retry instead of a silent $0.00', async () => {
    server.use(
      http.get('*/api/balance/', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    );
    render(<CoinExchangeModal exchangeRate={10} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/couldn't load your money balance/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('$0.00')).toBeNull();
  });
});
