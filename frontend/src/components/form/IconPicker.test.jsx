import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IconPicker from './IconPicker';

function Picker({ initialValue = '' }) {
  const [value, setValue] = useState(initialValue);
  return <IconPicker value={value} onChange={setValue} />;
}

describe('IconPicker', () => {
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
    render(<IconPicker value="📖" onChange={vi.fn()} disabled />);
    expect(screen.getByRole('textbox', { name: 'Icon' })).toBeDisabled();
    for (const button of screen.getAllByRole('button', { hidden: true })) {
      expect(button).toBeDisabled();
    }
  });

  it('keeps the owning field label, help, input limit and custom options', async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    render(<IconPicker
      label="Icon (optional emoji)" id="savings-icon" placeholder="🎯" maxLength={50}
      helpText="Optional savings goal icon" value="🦄" onChange={change}
      options={[[ '🎯', 'Target' ]]}
    />);
    const input = screen.getByLabelText('Icon (optional emoji)');
    expect(input).toHaveAttribute('id', 'savings-icon');
    expect(input).toHaveAttribute('placeholder', '🎯');
    expect(input).toHaveAttribute('maxlength', '50');
    expect(input).toHaveAccessibleDescription('Optional savings goal icon');
    expect(input).toHaveValue('🦄');
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    const choices = screen.getByRole('group', { name: 'Suggested icons' });
    expect(within(choices).getAllByRole('button')).toHaveLength(1);
    await user.click(within(choices).getByRole('button', { name: 'Target' }));
    expect(change).toHaveBeenCalledWith('🎯');
  });

  it('keeps multiple pickers independently labeled and expanded', async () => {
    const user = userEvent.setup();
    render(<>
      <IconPicker label="Reward icon" value="🎁" onChange={vi.fn()} />
      <IconPicker label="Chore icon" value="🧹" onChange={vi.fn()} />
    </>);
    const [reward, chore] = screen.getAllByRole('button', { name: 'Choose icon' });
    expect(reward.getAttribute('aria-controls')).not.toBe(chore.getAttribute('aria-controls'));
    await user.click(reward);
    expect(reward).toHaveAttribute('aria-expanded', 'true');
    expect(chore).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getAllByRole('group', { name: 'Suggested icons' })).toHaveLength(1);
    expect(screen.getByLabelText('Reward icon').id).not.toBe(screen.getByLabelText('Chore icon').id);
  });
});
