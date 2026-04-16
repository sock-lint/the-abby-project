import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfirmDialog from './ConfirmDialog.jsx';

describe('ConfirmDialog', () => {
  it('renders title, message, and default confirm label', () => {
    render(<ConfirmDialog title="Delete?" message="Are you sure?" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText('Delete?')).toBeInTheDocument();
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('renders a custom confirm label', () => {
    render(<ConfirmDialog title="x" message="y" confirmLabel="Nuke" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole('button', { name: 'Nuke' })).toBeInTheDocument();
  });

  it('fires onConfirm', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDialog title="x" message="y" onConfirm={onConfirm} onCancel={() => {}} />);
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('fires onCancel from the Cancel button and the backdrop', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ConfirmDialog title="x" message="y" onConfirm={() => {}} onCancel={onCancel} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    // Click the backdrop (first motion.div with modal-ink-wash class).
    const backdrop = container.querySelector('.modal-ink-wash');
    await user.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
