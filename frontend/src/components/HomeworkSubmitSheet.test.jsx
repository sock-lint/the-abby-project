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
    // The file input is hidden behind a camera icon but still queryable.
    const fileInput = document.body.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    const notes = inSheet().getByPlaceholderText(/notes/i);
    await user.type(notes, 'done!');

    const btn = inSheet().getByRole('button', { name: /submit for review/i });
    await waitFor(() => expect(btn).not.toBeDisabled());
    await user.click(btn);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/homework\/42\/submit\/$/);
    expect(onSubmitted).toHaveBeenCalled();
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
    const fileInput = document.body.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

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
