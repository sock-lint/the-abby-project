import { beforeEach, describe, expect, it, vi } from 'vitest';
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
// global. Default: supported, never fires. Per-test overrides assign to
// `speech.current` before rendering.
const speech = vi.hoisted(() => ({ current: { supported: true } }));
vi.mock('../../hooks/useSpeechDictation.js', () => ({
  useSpeechDictation: () => speech.current,
}));

beforeEach(() => {
  speech.current = { supported: true };
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

  // Declining the mic prompt flips isListening on and straight back off. With
  // no visible feedback the button just reads as broken.
  it('explains a blocked mic instead of failing silently', () => {
    speech.current = {
      supported: true, isListening: false, interim: '', error: 'not-allowed',
      start: vi.fn(), stop: vi.fn(),
    };
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    expect(
      within(getDialog()).getByText(/mic is blocked/i),
    ).toBeInTheDocument();
  });

  it('falls back to a generic hint for an unrecognized dictation error', () => {
    speech.current = {
      supported: true, isListening: false, interim: '', error: 'weird-code',
      start: vi.fn(), stop: vi.fn(),
    };
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    expect(
      within(getDialog()).getByText(/dictation stopped/i),
    ).toBeInTheDocument();
  });

  it('shows no dictation hint when nothing has gone wrong', () => {
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    expect(within(getDialog()).queryByText(/mic is blocked/i)).toBeNull();
    expect(within(getDialog()).queryByText(/dictation stopped/i)).toBeNull();
  });

  it('renders the privacy whisper line', () => {
    renderWithProviders(
      <JournalEntryFormModal mode="create" onClose={() => {}} onSaved={() => {}} />,
    );
    const dialog = getDialog();
    expect(within(dialog).getByText(/private to you/i)).toBeInTheDocument();
  });

  it('locks a prior-day entry into read-only mode (no Save button, only Close)', async () => {
    // Compute a local-date string for yesterday — matches the modal's
    // ``new Date().toLocaleDateString('en-CA')`` lock check.
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000)
      .toLocaleDateString('en-CA');
    renderWithProviders(
      <JournalEntryFormModal
        mode="edit"
        entry={{
          id: 17,
          title: 'Yesterday',
          summary: "yesterday's thoughts",
          kind: 'journal',
          occurred_on: yesterday,
        }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog', { name: /journal entry — locked/i });
    // No Save / Update button — locked entries can't be edited.
    expect(within(dialog).queryByRole('button', { name: /update entry/i })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: /save entry/i })).toBeNull();
    // Close (the only ghost form button) is present — BottomSheet has a
    // duplicate Close icon-button on its header, so just assert ≥1 match.
    expect(within(dialog).getAllByRole('button', { name: /^close$/i }).length)
      .toBeGreaterThanOrEqual(1);
    // Body and title are disabled.
    expect(within(dialog).getByLabelText(/title/i)).toBeDisabled();
    expect(within(dialog).getByLabelText(/mind/i)).toBeDisabled();
    // The lock chip ("part of your chronicle now") is rendered.
    expect(
      within(dialog).getByText(/part of your chronicle now/i),
    ).toBeInTheDocument();
  });

  it("today's entry stays editable (Save/Update + textarea enabled)", async () => {
    const today = new Date().toLocaleDateString('en-CA');
    renderWithProviders(
      <JournalEntryFormModal
        mode="edit"
        entry={{
          id: 17,
          title: 'Today',
          summary: "today's thoughts",
          kind: 'journal',
          occurred_on: today,
        }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog', { name: /edit your journal entry/i });
    expect(within(dialog).getByLabelText(/mind/i)).not.toBeDisabled();
    expect(within(dialog).getByRole('button', { name: /update entry/i })).toBeInTheDocument();
  });

  it('flips to edit mode when POST returns 409 with the existing entry', async () => {
    // 409 path: the child is in create mode and submits, but the backend
    // (via the unique-per-day constraint) reports that today's entry
    // already exists. The modal should swap to edit mode, preserve the
    // child's in-flight words, and surface a friendly error.
    // Today's entry — use a real "today" date so the modal's lock-after-
    // midnight gate (compares entry.occurred_on to today's local date)
    // doesn't kick in. The 409 path always returns today's row by
    // construction; matching here keeps that contract honest.
    const existing = {
      id: 77,
      kind: 'journal',
      is_private: true,
      title: 'Earlier today',
      summary: 'Some earlier thoughts.',
      occurred_on: new Date().toLocaleDateString('en-CA'),
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
