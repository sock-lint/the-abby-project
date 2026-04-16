import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RequestChangesModal from './RequestChangesModal.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('RequestChangesModal', () => {
  it('submits notes', async () => {
    const onSubmit = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<RequestChangesModal onClose={vi.fn()} onSubmit={onSubmit} />);
    await user.type(screen.getByPlaceholderText(/should they fix/i), 'fix it');
    await user.click(screen.getByRole('button', { name: /send/i }));
    expect(onSubmit).toHaveBeenCalledWith('fix it');
  });

  it('cancel closes the modal', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RequestChangesModal onClose={onClose} onSubmit={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
