import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EditProjectModal from './EditProjectModal.jsx';
import { server } from '../../../test/server.js';
import { buildProject } from '../../../test/factories.js';
import { spyHandler } from '../../../test/spy.js';
import { useSpace } from '../../../hooks/useSpace';
import { selectDropdown } from '../../../test/selectDropdown';
import { getProject } from '../../../api';
import personalRateDefault from '../../../../../contracts/api/fixtures/parent-personal-project-rate-default.json';
import familyExplicitZero from '../../../../../contracts/api/fixtures/parent-family-project-explicit-zero.json';

vi.mock('../../../hooks/useSpace', () => ({ useSpace: vi.fn() }));

beforeEach(() => useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: false }));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('EditProjectModal', () => {
  it.each([[personalRateDefault, true], [familyExplicitZero, false]])('uses the raw project $0.id response to retain an explicit zero or restore the child default', async (fixture, inherited) => {
    const user = userEvent.setup();
    const update = spyHandler('patch', `*/api/projects/${fixture.id}/`, fixture);
    server.use(http.get(`*/api/projects/${fixture.id}/`, () => HttpResponse.json(fixture)),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    const project = await getProject(fixture.id);
    expect(project).toEqual(fixture);
    render(<EditProjectModal project={project} onClose={vi.fn()} onSaved={vi.fn()} />);
    await selectDropdown(user, screen.getByLabelText('Assign To'), '7');
    expect(screen.getByLabelText('Rate Override ($)')).toHaveDisplayValue(inherited ? '' : '0.00');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body.assigned_to_id).toBe('7');
    if (inherited) expect(update.calls[0].body).not.toHaveProperty('hourly_rate_override');
    else expect(update.calls[0].body.hourly_rate_override).toBe('0.00');
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_is_personal_default');
  });

  it('shows the current parent assignment and clears its untouched zero rate when unassigning', async () => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent', display_name: 'Parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: true })} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText('Assign To')).toHaveTextContent('Parent');
    await selectDropdown(user, screen.getByLabelText('Assign To'), 'Unassigned');
    expect(screen.getByLabelText('Rate Override ($)')).toHaveDisplayValue('');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: null });
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_override');
  });

  it('preserves a deliberately chosen zero override when unassigning parent work', async () => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent', display_name: 'Parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: true })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.clear(screen.getByLabelText('Rate Override ($)'));
    await user.type(screen.getByLabelText('Rate Override ($)'), '0');
    await selectDropdown(user, screen.getByLabelText('Assign To'), 'Unassigned');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: null, hourly_rate_override: '0' });
  });

  it('restores a child’s default hourly rate when assigning an unchanged personal zero override', async () => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: true })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await selectDropdown(user, screen.getByLabelText('Assign To'), '7');
    expect(screen.getByLabelText('Rate Override ($)')).toHaveDisplayValue('');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: '7' });
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_override');
  });

  it.each(['before', 'after'])('preserves an intentionally entered zero rate %s choosing the child', async (when) => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: true })} onClose={vi.fn()} onSaved={vi.fn()} />);
    const editRate = async () => { await user.clear(screen.getByLabelText('Rate Override ($)')); await user.type(screen.getByLabelText('Rate Override ($)'), '0'); };
    if (when === 'before') await editRate();
    await selectDropdown(user, screen.getByLabelText('Assign To'), '7');
    if (when === 'after') await editRate();
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: '7', hourly_rate_override: '0' });
  });

  it.each([
    [false, '7'], [false, 'Unassigned'], [undefined, '7'], [undefined, 'Unassigned'],
  ])('preserves saved Family zero when personal-default is %s and assigning %s', async (personalDefault, nextOwner) => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: personalDefault })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await selectDropdown(user, screen.getByLabelText('Assign To'), nextOwner);
    expect(screen.getByLabelText('Rate Override ($)')).toHaveDisplayValue('0.00');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: nextOwner === 'Unassigned' ? null : '7', hourly_rate_override: '0.00' });
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_is_personal_default');
  });

  it('keeps an inherited personal default untouched during an unrelated Family edit', async () => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 99, role: 'parent' }, hourly_rate_override: '0.00', hourly_rate_is_personal_default: true })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.clear(screen.getByLabelText('Title'));
    await user.type(screen.getByLabelText('Title'), 'Updated notes');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ title: 'Updated notes', assigned_to_id: 99 });
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_override');
    expect(update.calls[0].body).not.toHaveProperty('hourly_rate_is_personal_default');
  });

  it('edits a parent’s own project without fetching children or sending family assignment and pay fields', async () => {
    useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: true });
    const user = userEvent.setup();
    const children = spyHandler('get', '*/api/children/', [{ id: 7, display_name: 'Child' }]);
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    const onSaved = vi.fn();
    server.use(children.handler, update.handler);
    render(<EditProjectModal project={buildProject({ id: 1, assigned_to: { id: 99, role: 'parent' } })} onClose={vi.fn()} onSaved={onSaved} />);
    for (const label of ['Assign To', 'Payment Kind', 'Bonus ($)', 'Rate Override ($)']) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
    await user.clear(screen.getByLabelText('Title'));
    await user.type(screen.getByLabelText('Title'), 'My feeder');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0]).toMatchObject({ method: 'PATCH', body: { title: 'My feeder', materials_budget: '0' } });
    expect(update.calls[0].url).toMatch(/\/api\/projects\/1\/$/);
    for (const field of ['assigned_to_id', 'payment_kind', 'bonus_amount', 'hourly_rate_override']) {
      expect(update.calls[0].body).not.toHaveProperty(field);
    }
    expect(children.calls).toHaveLength(0);
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it('keeps family assignment and pay controls and submits their values', async () => {
    const user = userEvent.setup();
    const update = spyHandler('patch', '*/api/projects/1/', { id: 1 });
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Child' }])), update.handler);
    render(<EditProjectModal project={buildProject({ assigned_to: { id: 7 } })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText('Assign To')).toHaveTextContent('Child'));
    await selectDropdown(user, screen.getByLabelText('Assign To'), '7');
    await user.clear(screen.getByLabelText('Bonus ($)'));
    await user.type(screen.getByLabelText('Bonus ($)'), '5');
    await user.type(screen.getByLabelText('Rate Override ($)'), '9');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to_id: 7, payment_kind: 'required', bonus_amount: '5', hourly_rate_override: '9' });
  });

  it('keeps a retired saved category readable and unchanged on an unrelated project edit', async () => {
    const user = userEvent.setup();
    const updates = [];
    server.use(
      http.get('*/api/categories/', () => HttpResponse.json([
        { id: 7, name: 'Earlier category', is_retired: true, available_for_new_choices: false },
        { id: 8, name: 'Current category', is_retired: false, available_for_new_choices: true },
      ])),
      http.patch('*/api/projects/1/', async ({ request }) => { updates.push(await request.json()); return HttpResponse.json({ id: 1 }); }),
    );
    render(<EditProjectModal project={buildProject({ id: 1, title: 'Old', category: { id: 7, name: 'Earlier category' } })} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Category' })).toHaveTextContent('Earlier category · Retired'));
    await user.clear(screen.getByLabelText('Title'));
    await user.type(screen.getByLabelText('Title'), 'Updated title');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(updates[0]).toMatchObject({ title: 'Updated title', category_id: 7 });
  });

  it('submits changes', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.patch(/\/api\/projects\/1\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(
      <EditProjectModal project={buildProject({ id: 1, title: 'Old' })} onClose={vi.fn()} onSaved={onSaved} />,
    );
    expect(screen.getByDisplayValue('Old')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
