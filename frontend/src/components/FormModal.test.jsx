import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FormModal from './FormModal.jsx';

describe('FormModal', () => {
  it('renders title and children via portal', () => {
    render(<FormModal title="Edit Chore" onClose={() => {}}><div>body</div></FormModal>);
    expect(screen.getByText('Edit Chore')).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('fires onClose from the seal button', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<FormModal title="t" onClose={onClose}><p /></FormModal>);
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('fires onClose when backdrop is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    // Portal renders into document.body, so query that root instead.
    render(<FormModal title="t" onClose={onClose}><p /></FormModal>);
    await user.click(document.body.querySelector('.modal-ink-wash'));
    expect(onClose).toHaveBeenCalled();
  });

  it('honors the size="md" prop', () => {
    render(<FormModal title="t" onClose={() => {}} size="md"><p /></FormModal>);
    expect(document.body.querySelector('.max-w-md')).toBeTruthy();
  });

  it('defaults to size="lg"', () => {
    render(<FormModal title="t" onClose={() => {}}><p /></FormModal>);
    expect(document.body.querySelector('.max-w-lg')).toBeTruthy();
  });

  it('honors scroll=false by removing overflow class', () => {
    render(<FormModal title="t" onClose={() => {}} scroll={false}><p /></FormModal>);
    expect(document.body.querySelector('.max-h-\\[85vh\\]')).toBeFalsy();
  });
});
