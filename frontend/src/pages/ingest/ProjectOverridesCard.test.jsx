import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProjectOverridesCard from './ProjectOverridesCard.jsx';

describe('ProjectOverridesCard', () => {
  it('renders draft title input and applies changes', async () => {
    const setDraft = vi.fn();
    const user = userEvent.setup();
    render(
      <ProjectOverridesCard
        draft={{ title: 'T' }} setDraft={setDraft}
        overrides={{ category_id: '', difficulty: 2, bonus_amount: '0', materials_budget: '0', due_date: '' }}
        setOverrides={vi.fn()}
        categories={[]}
      />,
    );
    expect(screen.getByDisplayValue('T')).toBeInTheDocument();
    await user.type(screen.getByDisplayValue('T'), 'x');
    expect(setDraft).toHaveBeenCalled();
  });
});
