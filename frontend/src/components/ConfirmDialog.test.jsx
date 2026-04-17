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

  it('exposes role=alertdialog with aria-modal, aria-labelledby, and aria-describedby', () => {
    render(
      <ConfirmDialog
        title="Delete reward"
        message="This cannot be undone."
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    const dialog = screen.getByRole('alertdialog', { name: 'Delete reward' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    // aria-describedby should point at an element containing the message text.
    const describedById = dialog.getAttribute('aria-describedby');
    expect(describedById).toBeTruthy();
    const descEl = document.getElementById(describedById);
    expect(descEl).toHaveTextContent('This cannot be undone.');
  });

  it('generates unique IDs for multiple stacked dialogs', () => {
    render(
      <>
        <ConfirmDialog title="A" message="aa" onConfirm={() => {}} onCancel={() => {}} />
        <ConfirmDialog title="B" message="bb" onConfirm={() => {}} onCancel={() => {}} />
      </>,
    );
    const dialogs = screen.getAllByRole('alertdialog');
    expect(dialogs).toHaveLength(2);
    expect(dialogs[0].getAttribute('aria-labelledby')).not.toBe(
      dialogs[1].getAttribute('aria-labelledby'),
    );
    expect(dialogs[0].getAttribute('aria-describedby')).not.toBe(
      dialogs[1].getAttribute('aria-describedby'),
    );
  });
});
