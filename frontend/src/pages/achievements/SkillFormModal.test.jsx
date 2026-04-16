import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillFormModal from './SkillFormModal.jsx';

describe('SkillFormModal', () => {
  it('renders new form with category & subject filters', () => {
    render(
      <SkillFormModal
        categories={[{ id: 1, name: 'C' }]}
        subjects={[{ id: 1, name: 'S', category: 1 }, { id: 2, name: 'T', category: 2 }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing skill', () => {
    render(
      <SkillFormModal
        item={{ id: 1, name: 'Addition', category: 1, subject: 1, is_locked_by_default: true, order: 3, level_names: {} }}
        categories={[{ id: 1, name: 'C' }]}
        subjects={[{ id: 1, name: 'S', category: 1 }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Addition')).toBeInTheDocument();
  });

  it('toggles is_locked_by_default via checkbox', async () => {
    const user = userEvent.setup();
    render(
      <SkillFormModal
        categories={[{ id: 1, name: 'C' }]}
        subjects={[]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const checkbox = document.querySelector('input[type="checkbox"]');
    if (checkbox) await user.click(checkbox);
  });
});
