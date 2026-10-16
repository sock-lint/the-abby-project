import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BadgeFormModal from './BadgeFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

describe('BadgeFormModal', () => {
  it.each(['create', 'edit'])('saves a selected icon when users %s a badge', async (mode) => {
    const user = userEvent.setup();
    const item = { id: 7, name: 'First song', description: 'Play a song', icon: '🦉✨', subject: 3, criteria_type: 'skill_level_reached', criteria_value: { level: 1 }, xp_bonus: 20, rarity: 'rare' };
    const path = mode === 'edit' ? /\/api\/badges\/7\/$/ : /\/api\/badges\/$/;
    const save = spyHandler(mode === 'edit' ? 'patch' : 'post', path, { id: 7 });
    server.use(save.handler);
    render(<BadgeFormModal item={mode === 'edit' ? item : undefined} subjects={[{ id: 3, name: 'Music' }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    if (mode === 'create') {
      await user.type(screen.getByRole('textbox', { name: 'Name' }), 'First song');
      await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Play a song');
    }
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Lightning', exact: true }));
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('⚡');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: mode === 'edit' ? 'Update' : 'Create', exact: true }));

    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(path);
    expect(save.calls[0].method).toBe(mode === 'edit' ? 'PATCH' : 'POST');
    expect(save.calls[0].body).toEqual({
      name: 'First song', description: 'Play a song', icon: '⚡', subject: mode === 'edit' ? 3 : null,
      criteria_type: mode === 'edit' ? 'skill_level_reached' : 'projects_completed',
      criteria_value: mode === 'edit' ? { level: 1 } : {}, xp_bonus: mode === 'edit' ? 20 : 0,
      rarity: mode === 'edit' ? 'rare' : 'common',
    });
  });

  it('preserves a custom badge icon when editing other fields', async () => {
    const user = userEvent.setup();
    const save = spyHandler('patch', /\/api\/badges\/7\/$/, { id: 7 });
    server.use(save.handler);
    render(<BadgeFormModal item={{ id: 7, name: 'First song', description: 'Play a song', icon: '🦉✨', subject: 3, criteria_type: 'skill_level_reached', criteria_value: { level: 1 }, xp_bonus: 20, rarity: 'rare' }} subjects={[{ id: 3, name: 'Music' }]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('textbox', { name: 'Icon', exact: true })).toHaveValue('🦉✨');
    await user.type(screen.getByRole('textbox', { name: 'Name' }), ' award');
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/badges\/7\/$/);
    expect(save.calls[0].body).toEqual({ name: 'First song award', description: 'Play a song', icon: '🦉✨', subject: 3, criteria_type: 'skill_level_reached', criteria_value: { level: 1 }, xp_bonus: 20, rarity: 'rare' });
  });

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
