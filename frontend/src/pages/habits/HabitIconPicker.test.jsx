import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HabitIconPicker from './HabitIconPicker';

function Picker({ initialValue = '' }) {
  const [value, setValue] = useState(initialValue);
  return <HabitIconPicker value={value} onChange={setValue} />;
}

describe('HabitIconPicker', () => {
  it('shows choices on demand and updates one selected icon without submitting', async () => {
    const user = userEvent.setup();
    const submit = vi.fn((event) => event.preventDefault());
    render(<form onSubmit={submit}><Picker /></form>);

    const choose = screen.getByRole('button', { name: 'Choose icon' });
    expect(choose).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('group', { name: 'Suggested icons' })).not.toBeInTheDocument();
    await user.click(choose);

    const choices = screen.getByRole('group', { name: 'Suggested icons' });
    await user.click(within(choices).getByRole('button', { name: 'Toothbrush' }));
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveValue('🪥');
    expect(within(choices).getAllByRole('button', { pressed: true })).toHaveLength(1);
    expect(within(choices).getByRole('button', { name: 'Toothbrush' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(within(choices).getByRole('button', { name: 'Book' }));
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveValue('📖');
    expect(within(choices).getAllByRole('button', { pressed: true })).toHaveLength(1);
    expect(within(choices).getByRole('button', { name: 'Toothbrush' })).toHaveAttribute('aria-pressed', 'false');
    expect(submit).not.toHaveBeenCalled();

    await user.click(choose);
    expect(choose).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveValue('📖');
  });

  it('preserves custom icons and clears preset selection when a custom icon is typed', async () => {
    const user = userEvent.setup();
    render(<Picker initialValue="🦄" />);
    const input = screen.getByRole('textbox', { name: 'Icon' });
    expect(input).toHaveValue('🦄');
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    expect(screen.queryByRole('button', { pressed: true })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Water' }));
    await user.clear(input);
    await user.type(input, '☀️');
    expect(screen.queryByRole('button', { pressed: true })).not.toBeInTheDocument();
    expect(input).toHaveValue('☀️');
  });

  it('supports keyboard selection with Enter and Space', async () => {
    const user = userEvent.setup();
    render(<Picker initialValue="📖" />);
    await user.tab();
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveFocus();
    await user.tab();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: 'Choose icon' })).toHaveAttribute('aria-expanded', 'true');
    await user.tab();
    expect(screen.getByRole('button', { name: 'Lightning' })).toHaveFocus();
    await user.keyboard(' ');
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveValue('⚡');
    await user.tab();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('textbox', { name: 'Icon' })).toHaveValue('🪥');
  });

  it('disables icon edits and choices while saving', () => {
    render(<HabitIconPicker value="📖" onChange={vi.fn()} disabled />);
    expect(screen.getByRole('textbox', { name: 'Icon' })).toBeDisabled();
    for (const button of screen.getAllByRole('button', { hidden: true })) {
      expect(button).toBeDisabled();
    }
  });
});
