import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import MovementSessionLogModal from './MovementSessionLogModal';

function stubTypes(types) {
  server.use(
    http.get('*/api/movement-types/', () =>
      HttpResponse.json(
        types ?? [
          {
            id: 1, name: 'Run', icon: '🏃', slug: 'run',
            default_intensity: 'medium', is_active: true, order: 0, skill_tags: [],
          },
          {
            id: 2, name: 'Yoga', icon: '🧘', slug: 'yoga',
            default_intensity: 'low', is_active: true, order: 1, skill_tags: [],
          },
          {
            id: 3, name: 'Soccer practice', icon: '⚽', slug: 'soccer-practice',
            default_intensity: 'high', is_active: true, order: 2, skill_tags: [],
          },
        ],
      ),
    ),
  );
}

describe('MovementSessionLogModal', () => {
  it('renders the activity picker populated from /api/movement-types/', async () => {
    stubTypes();
    renderWithProviders(<MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => {
      const picker = screen.getByRole('combobox', { name: /what did you do/i });
      expect(picker).not.toBeDisabled();
    });

    const picker = screen.getByRole('combobox', { name: /what did you do/i });
    const options = within(picker).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(expect.arrayContaining([
      expect.stringMatching(/Run/),
      expect.stringMatching(/Yoga/),
      expect.stringMatching(/Soccer practice/),
    ]));
  });

  it('seeds intensity from the picked type default (yoga → low)', async () => {
    stubTypes();
    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });

    const picker = screen.getByRole('combobox', { name: /what did you do/i });
    await user.selectOptions(picker, '2'); // yoga

    const intensity = screen.getByRole('combobox', { name: /how hard/i });
    await waitFor(() => expect(intensity).toHaveValue('low'));
  });

  it('submits POST /api/movement-sessions/ with the right body shape', async () => {
    stubTypes();
    const spy = spyHandler('post', /\/api\/movement-sessions\/$/, { id: 99 });
    server.use(spy.handler);

    const onSaved = vi.fn();
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={onClose} onSaved={onSaved} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });

    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '1',
    );
    // The default duration is 30; default intensity gets seeded to medium
    // (Run.default_intensity). Submit straight away.
    const submit = screen.getByRole('button', { name: /log session/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/movement-sessions\/$/);
    expect(spy.calls[0].body).toMatchObject({
      movement_type_id: 1,
      duration_minutes: 30,
      intensity: 'medium',
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('disables submit until a movement type is picked', async () => {
    stubTypes();
    renderWithProviders(<MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });

    const submit = screen.getByRole('button', { name: /log session/i });
    expect(submit).toBeDisabled();
  });
});
