import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CategoryFormModal from './CategoryFormModal.jsx';
import { server } from '../../test/server.js';

describe('CategoryFormModal', () => {
  it('renders new form', () => {
    render(<CategoryFormModal onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing', () => {
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#f00', description: 'x' }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Art')).toBeInTheDocument();
  });

  it('submits on save', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(http.post('*/api/categories/', () => HttpResponse.json({ id: 1 })));
    render(<CategoryFormModal onClose={() => {}} onSaved={onSaved} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Science');
    await user.click(screen.getByRole('button', { name: /create|save/i }));
  });
});
