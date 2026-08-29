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
    render(<ConfirmDialog title="x" message="y" onConfirm={() => {}} onCancel={onCancel} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    // Backdrop is portaled to document.body as a sibling of the centering
    // wrapper — not a descendant of the RTL container.
    const backdrop = document.querySelector('.modal-ink-wash');
    await user.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it('renders the backdrop below the card so clicks reach the confirm button', () => {
    // Structural guard: jsdom can't hit-test CSS, but we can lock in the
    // pattern that prevents the backdrop from painting over the card —
    // pointer-events-none on the centering wrapper + pointer-events-auto
    // on the alertdialog. If a refactor drops either, this fails.
    render(<ConfirmDialog title="x" message="y" onConfirm={() => {}} onCancel={() => {}} />);
    const dialog = screen.getByRole('alertdialog');
    expect(dialog.className).toMatch(/pointer-events-auto/);
    expect(dialog.parentElement.className).toMatch(/pointer-events-none/);
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

  it('autofocuses the confirm button so Enter triggers onConfirm', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDialog title="x" message="y" onConfirm={onConfirm} onCancel={() => {}} />);
    const confirmBtn = screen.getByRole('button', { name: 'Delete' });
    expect(document.activeElement).toBe(confirmBtn);
    await user.keyboard('{Enter}');
    expect(onConfirm).toHaveBeenCalled();
  });

  // The escape hatch next to a destructive seal used to be a hand-rolled
  // ~37px text button 8px from Delete — a slightly-off thumb landed on Delete.
  it('gives Cancel the shared 44px tap floor and keeps it clear of the seal', () => {
    render(<ConfirmDialog title="x" message="y" onConfirm={() => {}} onCancel={() => {}} />);
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const confirm = screen.getByRole('button', { name: 'Delete' });
    expect(cancel.className).toContain('min-h-11');
    expect(confirm.className).toContain('min-h-11');
    expect(cancel.parentElement.className).toContain('gap-4');
  });

  // Standalone the wash belongs below the z-50 card; stacked over an open
  // BottomSheet (also z-50) it has to clear the sheet or the "modal" dialog
  // leaves the sheet undimmed and fully tappable.
  it('raises the backdrop into the z-50 tier when stacked', () => {
    const { unmount } = render(
      <ConfirmDialog title="x" message="y" onConfirm={() => {}} onCancel={() => {}} />,
    );
    expect(document.querySelector('.modal-ink-wash').className).toContain('z-40');
    unmount();

    render(<ConfirmDialog stacked title="x" message="y" onConfirm={() => {}} onCancel={() => {}} />);
    expect(document.querySelector('.modal-ink-wash').className).toContain('z-50');
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
