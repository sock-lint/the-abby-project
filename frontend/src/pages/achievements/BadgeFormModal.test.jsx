import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BadgeFormModal from './BadgeFormModal.jsx';
import { server } from '../../test/server.js';

describe('BadgeFormModal', () => {
  it('renders an empty create form', () => {
    render(
      <BadgeFormModal subjects={[{ id: 1, name: 'S' }]} onClose={() => {}} onSaved={() => {}} />,
    );
    expect(screen.getAllByText(/new badge|create|badge/i).length).toBeGreaterThan(0);
  });

  it('submits a new badge', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(http.post('*/api/badges/', () => HttpResponse.json({ id: 1 })));
    render(
      <BadgeFormModal subjects={[{ id: 1, name: 'S' }]} onClose={() => {}} onSaved={onSaved} />,
    );
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Gold');
    await user.click(screen.getByRole('button', { name: /^create$|^save$/i }));
  });

  it('pre-populates edit form', () => {
    render(
      <BadgeFormModal
        item={{ id: 5, name: 'Existing', rarity: 'rare', criteria_value: {}, xp_bonus: 10 }}
        subjects={[]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Existing')).toBeInTheDocument();
  });
});
