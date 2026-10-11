import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, renderWithProviders, screen, waitFor, within } from '../test/render';
import AddToCalendar from './AddToCalendar';

const EVENT = { id: 'homework:42', title: 'Science project due', start: '2026-12-31', path: '/quests?tab=study' };

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function stubDownload() {
  const NativeURL = URL;
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = vi.fn(() => 'blob:calendar-copy');
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
}

function readBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

describe('AddToCalendar', () => {
  it.each([undefined, null, { ...EVENT, start: undefined }, { ...EVENT, start: '2026-02-30' }])('hides when the date is missing or invalid: %o', (event) => {
    const { container } = renderWithProviders(<AddToCalendar event={event} />, { withAuth: false });
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the provider chooser with a contextual trigger and an actual Google event link', async () => {
    const { user } = renderWithProviders(<AddToCalendar event={EVENT} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add Science project due to calendar' }));
    const dialog = screen.getByRole('dialog', { name: 'Add to calendar' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByText('Science project due')).toBeInTheDocument();
    expect(within(dialog).getByText(/All day/)).toBeInTheDocument();
    expect(within(dialog).getByText(/one-time copy/)).toBeInTheDocument();
    const google = within(dialog).getByRole('link', { name: 'Google Calendar' });
    const url = new URL(google.href);
    expect(url.searchParams.get('text')).toBe(EVENT.title);
    expect(url.searchParams.get('dates')).toBe('20261231/20270101');
    expect(google).toHaveAttribute('target', '_blank');
    expect(google).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(dialog).getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeEnabled();
    expect(within(dialog).getByText(/import it in Calendar on your Mac/)).toBeInTheDocument();
  });

  it('downloads the event shown in the dialog when Apple Calendar is chosen', async () => {
    stubDownload();
    const { user } = renderWithProviders(<AddToCalendar event={{ ...EVENT, start: '2026-10-11T10:00:00-07:00' }} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add Science project due to calendar' }));
    await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce();
    const file = await readBlob(URL.createObjectURL.mock.calls[0][0]);
    expect(file).toContain('SUMMARY:Science project due\r\n');
    expect(file).toContain('DTSTART:20261011T170000Z\r\n');
    expect(file).toContain('DTEND:20261011T173000Z\r\n');
  });

  it('uses shared modal focus trapping and restores its opener on Escape', async () => {
    const { user } = renderWithProviders(<AddToCalendar event={EVENT} />, { withAuth: false });
    const trigger = screen.getByRole('button', { name: 'Add Science project due to calendar' });
    await user.click(trigger);
    const close = screen.getByRole('button', { name: /close/i });
    expect(close).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('link', { name: 'Google Calendar' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('selects one duty reminder date and prevents exports for schedule validation errors', async () => {
    const duty = { ...EVENT, id: 'chore:1', title: 'Feed cat', start: '2026-10-12' };
    const { user } = renderWithProviders(<AddToCalendar event={duty} dateEditable dateHelp="Choose a day in an active week." validateDate={(date) => date === '2026-10-19' ? 'This is an off week.' : null} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add Feed cat to calendar' }));
    const date = screen.getByLabelText('Reminder date');
    expect(date).toHaveValue('2026-10-12');
    expect(screen.getByText('Choose a day in an active week.')).toBeInTheDocument();
    fireEvent.change(date, { target: { value: '2026-10-19' } });
    expect(screen.getByRole('alert')).toHaveTextContent('This is an off week.');
    expect(date).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('link', { name: 'Google Calendar' })).not.toHaveAttribute('href');
    expect(screen.getByRole('link', { name: 'Google Calendar' })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeDisabled();
    fireEvent.change(date, { target: { value: '2026-10-26' } });
    expect(new URL(screen.getByRole('link', { name: 'Google Calendar' }).href).searchParams.get('dates')).toBe('20261026/20261027');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeEnabled();
    fireEvent.change(date, { target: { value: '' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a valid reminder date.');
    expect(screen.getByRole('button', { name: 'Apple Calendar (.ics)' })).toBeDisabled();
  });

  it('uses distinct stable import identities for separate selected duty dates', async () => {
    stubDownload();
    const { user } = renderWithProviders(<AddToCalendar event={EVENT} dateEditable />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add Science project due to calendar' }));
    await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
    await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
    fireEvent.change(screen.getByLabelText('Reminder date'), { target: { value: '2027-01-02' } });
    await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
    const files = await Promise.all(URL.createObjectURL.mock.calls.map(([blob]) => readBlob(blob)));
    const uids = files.map((file) => file.replace(/\r\n /g, '').match(/^UID:(.+)$/m)[1]);
    expect(uids[0]).toBe(uids[1]);
    expect(uids[2]).not.toBe(uids[0]);
    expect(files[2]).toContain('DTSTART;VALUE=DATE:20270102');
  });

  it('surfaces a browser download error without an unhandled rejection', async () => {
    stubDownload();
    URL.createObjectURL.mockImplementation(() => { throw new Error('Download unavailable'); });
    const { user } = renderWithProviders(<AddToCalendar event={EVENT} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add Science project due to calendar' }));
    await user.click(screen.getByRole('button', { name: 'Apple Calendar (.ics)' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The calendar download could not start. Please try again.'));
  });
});
