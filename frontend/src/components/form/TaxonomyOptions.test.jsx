import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SelectField from './SelectField';
import TaxonomyOptions from './TaxonomyOptions';
import { openDropdown } from '../../test/selectDropdown';

const entries = [
  { id: 7, name: 'Earlier category', is_retired: true, available_for_new_choices: false },
  { id: 8, name: 'Current category', is_retired: false, available_for_new_choices: true },
  { id: 9, name: 'Inherited unavailable', is_retired: false, available_for_new_choices: false },
];

describe('taxonomy choices', () => {
  it('distinguishes authored status-like names from a saved retired choice', async () => {
    const user = userEvent.setup();
    const changed = vi.fn();
    const colliding = [
      { id: 1, name: 'Practice', is_retired: true },
      { id: 2, name: 'Practice · Retired', is_retired: false },
      { id: 3, icon: 'Practice ·', name: 'Retired', is_retired: false },
    ];
    render(<SelectField label="Category" value={1} onChange={(event) => changed(event.target.value)}><TaxonomyOptions entries={colliding} selected={1} kind="category" /></SelectField>);
    const picker = screen.getByRole('combobox', { name: 'Category' });
    const choices = await openDropdown(user, picker);
    const labels = choices.getAllByRole('option').map((option) => option.textContent);
    expect(new Set(labels).size).toBe(3);
    expect(choices.getByRole('option', { name: 'Practice · Retired' })).toHaveAttribute('aria-disabled', 'true');
    await user.click(choices.getByRole('option', { name: '"Practice · Retired"' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith('2');
  });

  it('never visually rebinds a saved ID while retained metadata is unavailable', async () => {
    const user = userEvent.setup();
    render(<SelectField label="Category" value={7} onChange={vi.fn()}><option value="">None</option><TaxonomyOptions entries={[]} selected={7} kind="category" /></SelectField>);
    const picker = screen.getByRole('combobox', { name: 'Category' });
    expect(picker).toHaveTextContent('Retained category (#7) · not listed');
    expect((await openDropdown(user, picker)).getByRole('option', { name: 'Retained category (#7) · not listed' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('keeps a saved retired option readable and disabled while selecting another exact ID', async () => {
    const user = userEvent.setup();
    const changed = vi.fn();
    render(<SelectField label="Category" value={7} onChange={(event) => changed(event.target.value)}><TaxonomyOptions entries={entries} selected={7} kind="category" /></SelectField>);
    const picker = screen.getByRole('combobox', { name: 'Category' });
    expect(picker).toHaveTextContent('Earlier category · Retired');
    const choices = await openDropdown(user, picker);
    expect(choices.getByRole('option', { name: 'Earlier category · Retired' })).toHaveAttribute('aria-disabled', 'true');
    expect(choices.queryByRole('option', { name: /Inherited unavailable/ })).not.toBeInTheDocument();
    await user.click(choices.getByRole('option', { name: 'Current category' }));
    expect(changed).toHaveBeenCalledExactlyOnceWith('8');
  });

  it('offers neither retired nor inherited unavailable identities to a new selection', async () => {
    const user = userEvent.setup();
    render(<SelectField label="Category" value="" onChange={vi.fn()}><option value="">None</option><TaxonomyOptions entries={entries} kind="category" /></SelectField>);
    const choices = await openDropdown(user, screen.getByRole('combobox', { name: 'Category' }));
    expect(choices.getAllByRole('option').map((option) => option.textContent)).toEqual(['None', 'Current category']);
  });
});
