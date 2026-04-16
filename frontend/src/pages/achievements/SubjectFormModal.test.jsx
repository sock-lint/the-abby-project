import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import SubjectFormModal from './SubjectFormModal.jsx';

describe('SubjectFormModal', () => {
  it('renders new form', () => {
    render(<SubjectFormModal categories={[{ id: 1, name: 'C' }]} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getAllByRole('textbox').length).toBeGreaterThan(0);
  });

  it('edits existing', () => {
    render(
      <SubjectFormModal
        item={{ id: 1, name: 'Math', category: 1 }}
        categories={[{ id: 1, name: 'C' }]}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Math')).toBeInTheDocument();
  });
});
