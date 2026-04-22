import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillTagEditor from './SkillTagEditor';

const SKILLS = [
  { id: 1, name: 'Persistence', icon: '💪', category_name: 'Life Skills' },
  { id: 2, name: 'Time Management', icon: '⏳', category_name: 'Life Skills' },
  { id: 3, name: 'Knife Skills', icon: '🔪', category_name: 'Cooking' },
];

describe('SkillTagEditor', () => {
  it('renders the empty state when no tags', () => {
    render(<SkillTagEditor skills={SKILLS} value={[]} onChange={() => {}} />);
    expect(screen.getByText(/No skills tagged/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add skill/i })).toBeInTheDocument();
  });

  it('renders existing tags with weight dropdowns', () => {
    const value = [
      { skill_id: 1, xp_weight: 3 },
      { skill_id: 3, xp_weight: 1 },
    ];
    render(<SkillTagEditor skills={SKILLS} value={value} onChange={() => {}} />);
    // Two skill dropdowns + two weight dropdowns — 4 selects total
    expect(screen.getAllByRole('combobox')).toHaveLength(4);
    expect(screen.getByText(/total 4/i)).toBeInTheDocument();
  });

  it('adding a tag calls onChange with a new row', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SkillTagEditor skills={SKILLS} value={[]} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: /add skill/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0];
    expect(next).toHaveLength(1);
    expect(next[0]).toHaveProperty('skill_id');
    expect(next[0]).toHaveProperty('xp_weight', 1);
  });

  it('removing a tag calls onChange without that row', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const value = [
      { skill_id: 1, xp_weight: 3 },
      { skill_id: 2, xp_weight: 1 },
    ];
    render(<SkillTagEditor skills={SKILLS} value={value} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: /remove persistence/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0];
    expect(next).toHaveLength(1);
    expect(next[0].skill_id).toBe(2);
  });

  it('does not show the Add button once every skill is used', () => {
    const value = [
      { skill_id: 1, xp_weight: 1 },
      { skill_id: 2, xp_weight: 1 },
      { skill_id: 3, xp_weight: 1 },
    ];
    render(<SkillTagEditor skills={SKILLS} value={value} onChange={() => {}} />);
    expect(screen.queryByRole('button', { name: /add skill/i })).not.toBeInTheDocument();
  });

  it('weight dropdown change emits new weight', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const value = [{ skill_id: 1, xp_weight: 1 }];
    render(<SkillTagEditor skills={SKILLS} value={value} onChange={onChange} />);

    const weight = screen.getByLabelText(/Weight for tag 1/i);
    await user.selectOptions(weight, '3');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0][0]).toEqual({ skill_id: 1, xp_weight: 3 });
  });
});
