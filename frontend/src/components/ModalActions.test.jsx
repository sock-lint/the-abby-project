import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ModalActions from './ModalActions.jsx';

describe('ModalActions', () => {
  it('renders a right-aligned ghost Cancel + Save pair by default', () => {
    render(<ModalActions onClose={() => {}} />);
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const submit = screen.getByRole('button', { name: 'Save' });
    expect(cancel.parentElement.className).toContain('justify-end');
    expect(submit).toHaveAttribute('type', 'submit');
    // Both clear the app's 44px tap floor via <Button>.
    expect(cancel.className).toContain('min-h-11');
    expect(submit.className).toContain('min-h-11');
  });

  it('fires onClose from Cancel', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ModalActions onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('splits the row 50/50 with a solid Cancel in fullWidth mode', () => {
    render(<ModalActions fullWidth onClose={() => {}} submitLabel="Log it" />);
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const submit = screen.getByRole('button', { name: 'Log it' });
    expect(cancel.parentElement.className).not.toContain('justify-end');
    expect(cancel.className).toContain('flex-1');
    expect(submit.className).toContain('flex-1');
    // ghost reads as disabled next to a filled half — fullWidth uses secondary.
    expect(cancel.className).toContain('bg-ink-page-aged');
  });

  it('locks the row and shows the saving label while saving', () => {
    render(<ModalActions onClose={() => {}} saving savingLabel="Logging…" submitLabel="Log it" />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /logging/i })).toBeDisabled();
  });

  it('disables only the submit button when the form is incomplete', () => {
    render(<ModalActions onClose={() => {}} submitDisabled />);
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).not.toBeDisabled();
  });

  // The row lives in BottomSheet's sticky `footer` slot, which renders outside
  // the <form> it belongs to — without the association the submit is inert.
  it('submits a form it does not sit inside via formId', async () => {
    const onSubmit = vi.fn((e) => e.preventDefault());
    const user = userEvent.setup();
    render(
      <>
        <form id="detached-form" onSubmit={onSubmit}>
          <input type="text" aria-label="field" />
        </form>
        <ModalActions formId="detached-form" onClose={() => {}} submitLabel="Send" />
      </>,
    );
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
