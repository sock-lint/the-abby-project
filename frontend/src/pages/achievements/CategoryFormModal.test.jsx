import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('labels the color picker and shows the existing value', () => {
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#ff0000', description: 'x' }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const color = screen.getByLabelText('Color');
    expect(color).toHaveAttribute('type', 'color');
    expect(color).toHaveValue('#ff0000');
  });

  it('submits a color changed through the labelled picker', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const bodies = [];
    server.use(http.patch(/\/api\/categories\/1\/$/, async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({ id: 1 });
    }));
    render(
      <CategoryFormModal
        item={{ id: 1, name: 'Art', icon: '🎨', color: '#ff0000', description: 'x' }}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    );
    fireEvent.input(screen.getByLabelText('Color'), { target: { value: '#00ff00' } });
    await user.click(screen.getByRole('button', { name: /update/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({ name: 'Art', color: '#00ff00' });
  });
});
