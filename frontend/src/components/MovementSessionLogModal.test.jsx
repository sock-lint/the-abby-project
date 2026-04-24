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

function stubSkills(skills) {
  server.use(
    http.get('*/api/skills/', () =>
      HttpResponse.json(
        skills ?? [
          {
            id: 10, name: 'Endurance', icon: '🏃',
            category: 1, category_name: 'Physical',
            subject: 1, subject_name: 'Body Work',
          },
          {
            id: 11, name: 'Strength', icon: '💪',
            category: 1, category_name: 'Physical',
            subject: 1, subject_name: 'Body Work',
          },
          {
            id: 12, name: 'Flexibility', icon: '🧘',
            category: 1, category_name: 'Physical',
            subject: 1, subject_name: 'Body Work',
          },
          {
            id: 20, name: 'Cycling', icon: '🚴',
            category: 1, category_name: 'Physical',
            subject: 2, subject_name: 'Sports',
          },
          {
            id: 99, name: 'Soldering', icon: '🔌',
            category: 9, category_name: 'Making',
            subject: null, subject_name: null,
          },
        ],
      ),
    ),
  );
}

describe('MovementSessionLogModal', () => {
  it('renders the activity picker populated from /api/movement-types/', async () => {
    stubTypes();
    stubSkills();
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
    stubSkills();
    renderWithProviders(<MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });

    const submit = screen.getByRole('button', { name: /log session/i });
    expect(submit).toBeDisabled();
  });

  it('picker includes a "+ New activity…" option', async () => {
    stubTypes();
    stubSkills();
    renderWithProviders(<MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    const picker = screen.getByRole('combobox', { name: /what did you do/i });
    const options = within(picker).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(
      expect.arrayContaining([expect.stringMatching(/New activity/)]),
    );
  });

  it('selecting "+ New activity…" swaps to the create-type form', async () => {
    stubTypes();
    stubSkills();
    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '__new__',
    );

    expect(screen.getByRole('textbox', { name: /activity name/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /primary skill/i })).not.toBeDisabled();
    });
    // The session-log submit button is no longer in the DOM.
    expect(screen.queryByRole('button', { name: /log session/i })).not.toBeInTheDocument();
  });

  it('Back button returns to the log form without posting', async () => {
    stubTypes();
    stubSkills();
    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '__new__',
    );
    await user.click(screen.getByRole('button', { name: /^back$/i }));

    expect(screen.getByRole('button', { name: /log session/i })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /activity name/i })).not.toBeInTheDocument();
  });

  it('only Physical-category skills appear in the primary-skill picker', async () => {
    stubTypes();
    stubSkills();
    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '__new__',
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /primary skill/i })).not.toBeDisabled();
    });
    const primary = screen.getByRole('combobox', { name: /primary skill/i });
    const options = within(primary).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(expect.arrayContaining([
      expect.stringMatching(/Endurance/),
      expect.stringMatching(/Strength/),
      expect.stringMatching(/Cycling/),
    ]));
    // Soldering is in the Making category — must not appear.
    expect(options).not.toEqual(
      expect.arrayContaining([expect.stringMatching(/Soldering/)]),
    );
  });

  it('submits POST /api/movement-types/ with the right body and auto-selects the new type', async () => {
    stubTypes();
    stubSkills();
    const spy = spyHandler('post', /\/api\/movement-types\/$/, {
      id: 777, name: 'Parkour', icon: '🧗', slug: 'parkour',
      default_intensity: 'high', is_active: true, order: 0, skill_tags: [],
      created_by: 1,
    });
    server.use(spy.handler);
    // After the POST, the picker reload should include the new type so we
    // can assert the auto-select.
    server.use(
      http.get('*/api/movement-types/', () =>
        HttpResponse.json([
          {
            id: 1, name: 'Run', icon: '🏃', slug: 'run',
            default_intensity: 'medium', is_active: true, order: 0, skill_tags: [],
          },
          {
            id: 777, name: 'Parkour', icon: '🧗', slug: 'parkour',
            default_intensity: 'high', is_active: true, order: 1, skill_tags: [],
          },
        ]),
      ),
    );

    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '__new__',
    );
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /primary skill/i })).not.toBeDisabled();
    });

    await user.type(
      screen.getByRole('textbox', { name: /activity name/i }),
      'Parkour',
    );
    await user.selectOptions(
      screen.getByRole('combobox', { name: /default intensity/i }),
      'high',
    );
    await user.selectOptions(
      screen.getByRole('combobox', { name: /primary skill/i }),
      '11', // Strength
    );
    await user.selectOptions(
      screen.getByRole('combobox', { name: /secondary skill/i }),
      '12', // Flexibility
    );
    await user.click(screen.getByRole('button', { name: /add activity/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/movement-types\/$/);
    expect(spy.calls[0].body).toMatchObject({
      name: 'Parkour',
      default_intensity: 'high',
      primary_skill_id: 11,
      secondary_skill_id: 12,
    });

    // Back on the log form, auto-selected to the new type.
    await waitFor(() => {
      const picker = screen.getByRole('combobox', { name: /what did you do/i });
      expect(picker).toHaveValue('777');
    });
  });

  it('surfaces backend error inline when POST returns 400', async () => {
    stubTypes();
    stubSkills();
    server.use(
      http.post('*/api/movement-types/', () =>
        HttpResponse.json(
          { error: "An activity called 'Run' already exists." },
          { status: 400 },
        ),
      ),
    );

    const { user } = renderWithProviders(
      <MovementSessionLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });
    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '__new__',
    );
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /primary skill/i })).not.toBeDisabled();
    });

    await user.type(
      screen.getByRole('textbox', { name: /activity name/i }),
      'Run',
    );
    await user.selectOptions(
      screen.getByRole('combobox', { name: /primary skill/i }),
      '10',
    );
    await user.click(screen.getByRole('button', { name: /add activity/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/already exists/i);
    });
  });
});
