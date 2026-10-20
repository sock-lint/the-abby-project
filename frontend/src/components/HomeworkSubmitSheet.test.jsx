import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
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
  description: '',
  subject: 'reading',
  timeliness_preview: { timeliness: 'on_time' },
};

// Portal children live on document.body; scope queries accordingly.
const inSheet = () => within(document.body);

describe('HomeworkSubmitSheet', () => {
  it('shows assignment instructions before proof controls without exposing private notes', () => {
    render(<HomeworkSubmitSheet assignment={{
      ...assignment, description: 'Read chapter 4 and summarize its main idea.',
      notes: 'Private parent planning notes',
    }} onClose={vi.fn()} />);

    const instructions = screen.getByText('Read chapter 4 and summarize its main idea.');
    expect(instructions).toBeVisible();
    expect(instructions.compareDocumentPosition(screen.getByLabelText(/add proof photos/i)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText('Private parent planning notes')).not.toBeInTheDocument();
  });

  it('loads instructions for a Today summary and offers retry when the detail read fails', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const details = spyHandler('get', /\/api\/homework\/42\/$/, () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ detail: 'Instructions are unavailable.' }, { status: 503 })
        : { ...assignment, description: 'Explain the ending in your own words.', notes: 'Private parent planning notes' };
    });
    server.use(details.handler);
    render(<HomeworkSubmitSheet assignment={{ id: 42, title: 'Reading log' }} onClose={vi.fn()} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Instructions are unavailable.');
    await user.click(within(alert).getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Explain the ending in your own words.')).toBeVisible();
    expect(details.calls).toHaveLength(2);
    expect(details.calls[1].url).toMatch(/\/homework\/42\/$/);
    expect(screen.queryByText('Private parent planning notes')).not.toBeInTheDocument();
  });

  it('does not show late instructions from a closed assignment in a reopened sheet', async () => {
    let finishFirst;
    const firstResponse = new HttpResponse(new ReadableStream({
      start(controller) {
        finishFirst = () => {
          controller.enqueue(new TextEncoder().encode(JSON.stringify({ id: 42, description: 'Old assignment instructions' })));
          controller.close();
        };
      },
    }), { headers: { 'Content-Type': 'application/json' } });
    const first = spyHandler('get', /\/api\/homework\/42\/$/, firstResponse);
    const second = spyHandler('get', /\/api\/homework\/43\/$/, { id: 43, description: 'Current assignment instructions' });
    server.use(first.handler, second.handler);
    const view = render(<HomeworkSubmitSheet assignment={{ id: 42, title: 'First assignment' }} onClose={vi.fn()} />);
    try {
      await waitFor(() => expect(first.calls).toHaveLength(1));
      view.rerender(<HomeworkSubmitSheet assignment={null} onClose={vi.fn()} />);
      view.rerender(<HomeworkSubmitSheet assignment={{ id: 43, title: 'Second assignment' }} onClose={vi.fn()} />);
      expect(await screen.findByText('Current assignment instructions')).toBeVisible();
    } finally {
      await act(async () => { finishFirst(); });
    }
    expect(screen.queryByText('Old assignment instructions')).not.toBeInTheDocument();
  });

  it('renders nothing when assignment is null', () => {
    render(<HomeworkSubmitSheet assignment={null} onClose={vi.fn()} onSubmitted={vi.fn()} />);
    expect(screen.queryByRole('dialog', { name: 'Submit homework' })).not.toBeInTheDocument();
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

  it('submits a shareable proof link without photos and preserves its query and fragment', async () => {
    const user = userEvent.setup();
    let submitted;
    const spy = spyHandler('post', /\/api\/homework\/42\/submit\/$/, async ({ request }) => {
      submitted = await request.formData();
      return { ok: true };
    });
    server.use(spy.handler);
    const onSubmitted = vi.fn();
    render(<HomeworkSubmitSheet assignment={assignment} onSubmitted={onSubmitted} />);
    const link = 'https://drive.google.com/file/d/synthetic/view?usp=sharing#page=2';
    await user.type(screen.getByRole('textbox', { name: /proof link/i }), `  ${link}  `);
    await user.type(screen.getByRole('textbox', { name: /notes/i }), 'My finished worksheet');
    await user.click(screen.getByRole('button', { name: /submit for review/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
    expect(spy.calls).toHaveLength(1);
    expect(spy.calls[0].url).toMatch(/\/homework\/42\/submit\/$/);
    expect(spy.calls[0].method).toBe('POST');
    expect(Object.fromEntries(submitted)).toEqual({ proof_url: link, notes: 'My finished worksheet' });
    expect(screen.getByRole('textbox', { name: /proof link/i })).toHaveValue('');
  });

  it('can include a proof link alongside a photo', async () => {
    const user = userEvent.setup();
    let submitted;
    const spy = spyHandler('post', /\/api\/homework\/42\/submit\/$/, async ({ request }) => {
      submitted = await request.formData();
      return { ok: true };
    });
    server.use(spy.handler);
    const onSubmitted = vi.fn();
    render(<HomeworkSubmitSheet assignment={assignment} onSubmitted={onSubmitted} />);
    await user.upload(screen.getByLabelText(/add proof photos/i), new File(['x'], 'proof.jpg', { type: 'image/jpeg' }));
    await user.type(screen.getByRole('textbox', { name: /proof link/i }), 'https://docs.google.com/document/d/synthetic/edit');
    await user.click(screen.getByRole('button', { name: /submit for review/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
    expect(spy.calls).toHaveLength(1);
    expect(spy.calls[0].url).toMatch(/\/homework\/42\/submit\/$/);
    expect(submitted.get('proof_url')).toBe('https://docs.google.com/document/d/synthetic/edit');
    expect(submitted.getAll('images')).toHaveLength(1);
    expect(submitted.get('images').type).toBe('image/jpeg');
    expect(submitted.get('images').size).toBeGreaterThan(0);
  });

  it('keeps an invalid proof link for correction and sends no request even with a photo', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/homework\/42\/submit\/$/, { ok: true });
    server.use(spy.handler);
    render(<HomeworkSubmitSheet assignment={assignment} />);
    await user.upload(screen.getByLabelText(/add proof photos/i), new File(['x'], 'proof.jpg', { type: 'image/jpeg' }));
    const input = screen.getByRole('textbox', { name: /proof link/i });
    await user.type(input, 'javascript:alert(1)');
    await user.click(screen.getByRole('button', { name: /submit for review/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/valid http:\/\/ or https:\/\/ proof link/i);
    expect(input).toHaveValue('javascript:alert(1)');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: /remove photo/i })).toBeInTheDocument();
    expect(spy.calls).toHaveLength(0);
  });

  it('preserves the link and notes after an error until an explicit retry succeeds', async () => {
    const user = userEvent.setup();
    const submitted = [];
    const spy = spyHandler('post', /\/api\/homework\/42\/submit\/$/, async ({ request }) => {
      submitted.push(Object.fromEntries(await request.formData()));
      return submitted.length === 1
        ? HttpResponse.json({ error: 'Try again later.' }, { status: 503 })
        : { ok: true };
    });
    server.use(spy.handler);
    const onSubmitted = vi.fn();
    render(<HomeworkSubmitSheet assignment={assignment} onSubmitted={onSubmitted} />);
    const link = 'https://drive.google.com/file/d/synthetic/view';
    await user.type(screen.getByRole('textbox', { name: /proof link/i }), link);
    await user.type(screen.getByRole('textbox', { name: /notes/i }), 'Finished');
    await user.click(screen.getByRole('button', { name: /submit for review/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again later.');
    expect(screen.getByRole('textbox', { name: /proof link/i })).toHaveValue(link);
    expect(screen.getByRole('textbox', { name: /notes/i })).toHaveValue('Finished');
    expect(spy.calls).toHaveLength(1);
    expect(onSubmitted).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /submit for review/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
    expect(spy.calls).toHaveLength(2);
    expect(spy.calls.every((call) => /\/homework\/42\/submit\/$/.test(call.url))).toBe(true);
    expect(submitted).toEqual([
      { proof_url: link, notes: 'Finished' },
      { proof_url: link, notes: 'Finished' },
    ]);
  });

  it('guards a link-only draft when closing the sheet', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<HomeworkSubmitSheet assignment={assignment} onClose={onClose} />);
    const link = 'https://drive.google.com/file/d/synthetic/view';
    await user.type(screen.getByRole('textbox', { name: /proof link/i }), link);
    await user.keyboard('{Escape}');
    expect(await screen.findByRole('alertdialog', { name: 'Discard changes?' })).toBeVisible();
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('textbox', { name: /proof link/i })).toHaveValue(link);
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
    expect(inSheet().getByText(/^proof photos$/i)).toHaveAttribute('for', input.id);

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
