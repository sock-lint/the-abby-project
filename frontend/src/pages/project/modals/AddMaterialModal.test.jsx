import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddMaterialModal from './AddMaterialModal.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddMaterialModal', () => {
  it('submits a new material', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.post(/\/api\/projects\/5\/materials\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(<AddMaterialModal projectId={5} onClose={vi.fn()} onSaved={onSaved} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Wood');
    await user.click(screen.getByRole('button', { name: /^add material$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('shows an error when save fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(/\/api\/projects\/5\/materials\/$/, () =>
        HttpResponse.json({ error: 'bad' }, { status: 400 }),
      ),
    );
    render(<AddMaterialModal projectId={5} onClose={vi.fn()} onSaved={vi.fn()} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'x');
    await user.click(screen.getByRole('button', { name: /^add material$/i }));
    expect(await screen.findByText(/bad/i)).toBeInTheDocument();
  });
});
