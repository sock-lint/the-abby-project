import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import JournalEntryFormModal from './JournalEntryFormModal';

// Modal portals to document.body — query there, not the RTL container.
function getDialog() {
  return screen.getByRole('dialog', { name: /journal/i });
}

// Mock the speech hook so jsdom doesn't need a real SpeechRecognition
// global. Default: supported, never fires. Per-test overrides below.
vi.mock('../../hooks/useSpeechDictation.js', () => {
  let current = { supported: true };
  return {
    useSpeechDictation: () => current,
    __setSpeech: (value) => { current = value; },
  };
});

// Stub AnimatePresence so close-on-submit renders synchronously.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

describe('JournalEntryFormModal', () => {
  it('renders with textarea + mic + save controls', () => {
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    const dialog = getDialog();
    expect(within(dialog).getByLabelText(/title/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/mind/i)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /dictate/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /save entry/i })).toBeInTheDocument();
  });

  it('posts to /chronicle/journal/ on save', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/journal\/$/, {
      id: 42, kind: 'journal', is_private: true, title: 'Today',
    });
    server.use(spy.handler);
    const onSaved = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={onClose} onSaved={onSaved} />,
    );
    const dialog = getDialog();
    await user.type(
      within(dialog).getByLabelText(/mind/i),
      'Today I wrote a story.',
    );
    await user.click(within(dialog).getByRole('button', { name: /save entry/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ title: '', summary: 'Today I wrote a story.' });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it('patches to /chronicle/{id}/journal/ in edit mode', async () => {
    const spy = spyHandler('patch', /\/api\/chronicle\/\d+\/journal\/$/, {
      id: 7, title: 'Renamed',
    });
    server.use(spy.handler);
    const user = userEvent.setup();
    renderWithProviders(
      <JournalEntryFormModal
        mode="edit"
        entry={{ id: 7, title: 'Old', summary: 'x', kind: 'journal' }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const dialog = getDialog();
    const titleInput = within(dialog).getByLabelText(/title/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Renamed');
    await user.click(within(dialog).getByRole('button', { name: /update entry/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/chronicle\/7\/journal\/$/);
    expect(spy.calls[0].body).toEqual({ title: 'Renamed', summary: 'x' });
  });

  it('renders the privacy whisper line', () => {
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    const dialog = getDialog();
    expect(within(dialog).getByText(/private to you/i)).toBeInTheDocument();
  });

  it('flips to edit mode when POST returns 409 with the existing entry', async () => {
    // 409 path: the child is in create mode and submits, but the backend
    // (via the unique-per-day constraint) reports that today's entry
    // already exists. The modal should swap to edit mode, preserve the
    // child's in-flight words, and surface a friendly error.
    const existing = {
      id: 77,
      kind: 'journal',
      is_private: true,
      title: 'Earlier today',
      summary: 'Some earlier thoughts.',
      occurred_on: '2026-04-22',
    };
    server.use(
      http.post('*/api/chronicle/journal/', () =>
        HttpResponse.json(
          {
            detail: 'You already wrote a journal entry today. Edit it instead.',
            existing,
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    const dialog = getDialog();
    await user.type(within(dialog).getByLabelText(/mind/i), 'New thought I typed');
    await user.click(within(dialog).getByRole('button', { name: /save entry/i }));

    // Title flips to the BottomSheet title for edit mode.
    await waitFor(() =>
      expect(
        screen.getByRole('dialog', { name: /edit your journal entry/i }),
      ).toBeInTheDocument(),
    );
    // Primary button label flips.
    expect(
      screen.getByRole('button', { name: /update entry/i }),
    ).toBeInTheDocument();
    // Friendly 409 error — not a raw status code.
    expect(screen.getByRole('alert').textContent).toMatch(/already wrote today/i);
    // The in-flight text survives, appended after the existing body.
    expect(screen.getByLabelText(/mind/i).value).toContain('Some earlier thoughts.');
    expect(screen.getByLabelText(/mind/i).value).toContain('New thought I typed');
  });
});
