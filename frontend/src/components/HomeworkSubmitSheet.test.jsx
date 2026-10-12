import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HomeworkSubmitSheet from './HomeworkSubmitSheet';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const assignment = {
  id: 42,
  title: 'Reading log',
  subject: 'reading',
  timeliness_preview: { timeliness: 'on_time' },
};

// Portal children live on document.body; scope queries accordingly.
const inSheet = () => within(document.body);

describe('HomeworkSubmitSheet', () => {
  it('renders nothing when assignment is null', () => {
    render(<HomeworkSubmitSheet assignment={null} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    expect(screen.queryByText(/affix photographic evidence/i)).not.toBeInTheDocument();
  });

  it('renders the assignment title and subject when opened', () => {
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    expect(inSheet().getByText(/reading log/i)).toBeInTheDocument();
  });

  it('submit button is disabled until a proof image is added', async () => {
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    const btn = inSheet().getByRole('button', { name: /submit for review/i });
    expect(btn).toBeDisabled();
  });

  it('submitting posts images + notes to /homework/{id}/submit/ and calls onSubmitted', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/homework\/\d+\/submit\/$/, { ok: true });
    server.use(spy.handler);

    const onSubmitted = vi.fn();
    render(
      <HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={onSubmitted} />,
    );

    const file = new File(['x'], 'proof.jpg', { type: 'image/jpeg' });
    await user.upload(inSheet().getByLabelText(/add proof photos/i), file);

    const notes = inSheet().getByRole('textbox', { name: /notes/i });
    await user.type(notes, 'done!');

    const btn = inSheet().getByRole('button', { name: /submit for review/i });
    await waitFor(() => expect(btn).not.toBeDisabled());
    await user.click(btn);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/homework\/42\/submit\/$/);
    expect(onSubmitted).toHaveBeenCalled();
  });

  it('exposes the proof-photo input to keyboard and assistive tech', async () => {
    const user = userEvent.setup();
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);

    const input = inSheet().getByLabelText(/add proof photos/i);
    expect(input).toHaveAttribute('type', 'file');
    // display:none (Tailwind `hidden`) removes the input from the tab order.
    expect(input).not.toHaveClass('hidden');
    expect(input).toHaveClass('sr-only');

    // The visible heading names the same control.
    expect(inSheet().getByText(/proof photos \(required\)/i)).toHaveAttribute('for', input.id);

    // Reachable by Tab, not just programmatically focusable.
    for (let i = 0; i < 10 && document.activeElement !== input; i += 1) {
      await user.tab();
    }
    expect(input).toHaveFocus();
  });

  it('shows a focus ring on the picker tile when its input is focused', () => {
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    const tile = inSheet().getByLabelText(/add proof photos/i).closest('label');
    expect(tile).toHaveClass('focus-within:ring-2');
  });

  it('labels the notes field', () => {
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    expect(inSheet().getByRole('textbox', { name: 'Notes (optional)' })).toBeInTheDocument();
  });

  // The remove badge on a 64px thumbnail was a ~17px target — a kid
  // correcting a mis-picked photo mostly missed it.
  it('removes a proof photo through a 44px-floor remove control', async () => {
    const user = userEvent.setup();
    render(<HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={vi.fn()} />);

    const file = new File(['x'], 'proof.jpg', { type: 'image/jpeg' });
    await user.upload(inSheet().getByLabelText(/add proof photos/i), file);

    const remove = await inSheet().findByRole('button', { name: /remove photo/i });
    expect(remove.className).toContain('min-h-11');
    expect(remove.className).toContain('min-w-11');

    const submit = inSheet().getByRole('button', { name: /submit for review/i });
    await waitFor(() => expect(submit).not.toBeDisabled());

    await user.click(remove);
    expect(inSheet().queryByRole('button', { name: /remove photo/i })).not.toBeInTheDocument();
    expect(inSheet().getByRole('button', { name: /submit for review/i })).toBeDisabled();
  });

  it('surfaces an error when the submit request fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(/\/api\/homework\/\d+\/submit\/$/, () =>
        HttpResponse.json({ detail: 'Server down' }, { status: 500 }),
      ),
    );

    const onSubmitted = vi.fn();
    render(
      <HomeworkSubmitSheet assignment={assignment} onClose={vi.fn()} onSubmitted={onSubmitted} />,
    );

    const file = new File(['x'], 'proof.jpg', { type: 'image/jpeg' });
    await user.upload(inSheet().getByLabelText(/add proof photos/i), file);

    const btn = inSheet().getByRole('button', { name: /submit for review/i });
    await waitFor(() => expect(btn).not.toBeDisabled());
    await user.click(btn);

    // ErrorAlert surfaces the failure; onSubmitted must not fire.
    await waitFor(() => {
      expect(inSheet().getByText(/server down|could not submit/i)).toBeInTheDocument();
    });
    expect(onSubmitted).not.toHaveBeenCalled();
  });
});
