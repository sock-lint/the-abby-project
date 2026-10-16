import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlanDraftEditor from './PlanDraftEditor';

const initial = {
  milestones: [{ title: 'Prepare', description: '' }],
  steps: [{ title: 'Measure', description: '', milestone_index: 0 }],
  materials: [{ name: 'Wood', description: '', estimated_cost: '5.00' }],
};

describe('PlanDraftEditor', () => {
  it('edits material descriptions and keeps bounded fields accessible', async () => {
    function Editor() {
      const [plan, setPlan] = useState(initial);
      return <PlanDraftEditor plan={plan} onChange={setPlan} />;
    }
    render(<Editor />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Material 1 description'), 'Untreated wood');
    expect(screen.getByLabelText('Material 1 description')).toHaveValue('Untreated wood');
    expect(screen.getByLabelText('Milestone 1 title')).toHaveAttribute('maxLength', '200');
    expect(screen.getByLabelText('Step 1 description')).toHaveAttribute('maxLength', '4000');
    expect(screen.getByLabelText('Material 1 description')).toHaveAttribute('maxLength', '4000');
  });

  it('disables additions at each plan count limit and disables review controls during writes', () => {
    const plan = {
      milestones: Array.from({ length: 10 }, () => initial.milestones[0]),
      steps: Array.from({ length: 40 }, () => initial.steps[0]),
      materials: Array.from({ length: 40 }, () => initial.materials[0]),
    };
    const view = render(<PlanDraftEditor plan={plan} onChange={() => {}} />);
    for (const title of ['Milestones (10)', 'Steps (40)', 'Materials (40)']) {
      const section = screen.getByRole('heading', { name: title }).parentElement;
      expect(within(section).getByRole('button', { name: 'Add' })).toBeDisabled();
    }
    view.rerender(<PlanDraftEditor plan={initial} onChange={() => {}} disabled />);
    expect(screen.getByLabelText('Step 1 title')).toBeDisabled();
    expect(screen.getByLabelText('Material 1 estimated cost')).toBeDisabled();
  });
});
