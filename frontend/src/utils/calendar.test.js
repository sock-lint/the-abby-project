import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildCalendarFile, buildGoogleCalendarUrl, downloadCalendarFile } from './calendar';

const ORIGIN = { origin: 'https://abby.example' };
const NOW = new Date('2026-10-11T13:45:00Z');
const EVENT = { id: 'homework:42', title: 'Science project due', start: '2026-12-31', description: 'Bring the model.', path: '/quests?tab=study' };

function parseFile(content) {
  const lines = content.replace(/\r\n[ \t]/g, '').split('\r\n').filter(Boolean);
  const start = lines.indexOf('BEGIN:VEVENT');
  const end = lines.indexOf('END:VEVENT');
  return {
    lines,
    properties: Object.fromEntries(lines.slice(start + 1, end).map((line) => {
      const colon = line.indexOf(':');
      return [line.slice(0, colon), line.slice(colon + 1)];
    })),
  };
}

function readBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function stubDownload() {
  const NativeURL = URL;
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = vi.fn(() => 'blob:calendar-copy');
    static revokeObjectURL = vi.fn();
  });
  const downloads = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
    downloads.push({ filename: this.download, href: this.href, attached: this.isConnected });
  });
  return downloads;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Google Calendar event template', () => {
  it('keeps the Rewards printing destination in exports while stripping unrelated parameters', () => {
    const event = { ...EVENT, path: '/treasury?tab=forge&new=1&token=synthetic#private' };
    const file = buildCalendarFile(event, NOW, ORIGIN);
    expect(parseFile(file).properties.URL).toBe('https://abby.example/treasury?tab=forge');
    const url = new URL(buildGoogleCalendarUrl(event, ORIGIN));
    expect(url.searchParams.get('details')).toContain('https://abby.example/treasury?tab=forge');
    expect(file).not.toContain('synthetic');
    expect(file).not.toContain('new=1');
  });

  it('encodes the title, description, navigation link and exclusive all-day end', () => {
    const url = new URL(buildGoogleCalendarUrl({ ...EVENT, title: 'Science & art + music?' }, ORIGIN));
    expect(url.origin).toBe('https://calendar.google.com');
    expect(url.pathname).toBe('/calendar/r/eventedit');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      action: 'TEMPLATE',
      text: 'Science & art + music?',
      dates: '20261231/20270101',
      details: 'Bring the model.\n\nhttps://abby.example/quests?tab=study',
    });
  });

  it('supports an explicit exclusive multi-day end and February leap-day rollover', () => {
    const multiDay = new URL(buildGoogleCalendarUrl({ ...EVENT, start: '2028-02-28', end: '2028-03-02' }, ORIGIN));
    expect(multiDay.searchParams.get('dates')).toBe('20280228/20280302');
    const leapDay = new URL(buildGoogleCalendarUrl({ ...EVENT, start: '2028-02-29' }, ORIGIN));
    expect(leapDay.searchParams.get('dates')).toBe('20280229/20280301');
  });

  it('converts explicit offsets into UTC and defaults timed events to 30 minutes', () => {
    const url = new URL(buildGoogleCalendarUrl({ ...EVENT, start: '2026-12-31T23:45:00-07:00' }, ORIGIN));
    expect(url.searchParams.get('dates')).toBe('20270101T064500Z/20270101T071500Z');
    const range = new URL(buildGoogleCalendarUrl({ ...EVENT, start: '2026-10-11T10:00:00.123456+02:00', end: '2026-10-11T11:15:00+02:00' }, ORIGIN));
    expect(range.searchParams.get('dates')).toBe('20261011T080000Z/20261011T091500Z');
  });

  it.each([
    undefined, '', '2026-02-29', '2026-04-31', '2026-13-01', 'not-a-date',
    '2026-10-11T10:00:00', '2026-10-11T24:00:00Z', '2026-10-11T11:61:00Z',
    '2026-02-30T10:00:00Z', '2026-10-11T10:00:00+25:00',
  ])('rejects an invalid or ambiguous start: %s', (start) => {
    expect(buildGoogleCalendarUrl({ ...EVENT, start }, ORIGIN)).toBeNull();
    expect(buildCalendarFile({ ...EVENT, start }, NOW, ORIGIN)).toBeNull();
  });

  it.each([
    { end: '2026-12-30' }, { end: '2026-12-31' }, { end: 'invalid' },
    { end: '2027-01-01T00:00:00Z' },
    { start: '2026-10-11T10:00:00Z', end: '2026-10-11T09:00:00Z' },
    { start: '2026-10-11T10:00:00Z', end: '2026-10-11' },
  ])('rejects invalid or mismatched end values: %o', (range) => {
    expect(buildGoogleCalendarUrl({ ...EVENT, ...range }, ORIGIN)).toBeNull();
    expect(buildCalendarFile({ ...EVENT, ...range }, NOW, ORIGIN)).toBeNull();
  });

  it('exports only authored safe routes and allowlisted tabs, excluding credential query/hash fields', () => {
    const file = buildCalendarFile({ ...EVENT, path: '/quests?tab=study&token=synthetic-secret#synthetic-secret' }, NOW, ORIGIN);
    expect(parseFile(file).properties.URL).toBe('https://abby.example/quests?tab=study');
    expect(file).not.toContain('synthetic-secret');
    const url = new URL(buildGoogleCalendarUrl({ ...EVENT, path: '/quests?tab=unknown&token=synthetic-secret#synthetic-secret' }, ORIGIN));
    expect(url.searchParams.get('details')).toBe('Bring the model.\n\nhttps://abby.example/quests');
  });

  it.each(['https://outside.example/quests', '//outside.example/quests', '/\\outside.example', '/projects/../auth', '/quests%3Ftoken=secret'])('omits unsafe app paths: %s', (path) => {
    expect(parseFile(buildCalendarFile({ ...EVENT, path }, NOW, ORIGIN)).properties.URL).toBeUndefined();
    expect(new URL(buildGoogleCalendarUrl({ ...EVENT, path }, ORIGIN)).searchParams.get('details')).toBe('Bring the model.');
  });

  it('does not include current browser navigation or local auth data', () => {
    window.history.replaceState(null, '', '/auth?token=synthetic-current-token#synthetic-current-hash');
    localStorage.setItem('abby_auth_token', 'synthetic-local-token');
    const file = buildCalendarFile({ ...EVENT, path: undefined }, NOW);
    const url = buildGoogleCalendarUrl({ ...EVENT, path: undefined });
    for (const output of [file, url]) {
      expect(output).not.toContain('synthetic-current');
      expect(output).not.toContain('synthetic-local-token');
      expect(output).not.toContain('/auth');
    }
    window.history.replaceState(null, '', '/');
  });
});

describe('iCalendar file', () => {
  it('creates a standalone CRLF event with a stable UID, timestamp and date-only values', () => {
    const file = buildCalendarFile(EVENT, NOW, ORIGIN);
    const { properties, lines } = parseFile(file);
    expect(lines.slice(0, 4)).toEqual(['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//The Abby Project//Calendar Export//EN', 'CALSCALE:GREGORIAN']);
    expect(lines.slice(-2)).toEqual(['END:VEVENT', 'END:VCALENDAR']);
    expect(properties).toMatchObject({
      DTSTAMP: '20261011T134500Z',
      'DTSTART;VALUE=DATE': '20261231',
      'DTEND;VALUE=DATE': '20270101',
      SUMMARY: 'Science project due',
      DESCRIPTION: 'Bring the model.\\n\\nhttps://abby.example/quests?tab=study',
      URL: 'https://abby.example/quests?tab=study',
    });
    expect(file.endsWith('\r\n')).toBe(true);
    expect(file.replaceAll('\r\n', '')).not.toMatch(/[\r\n]/);
    expect(parseFile(buildCalendarFile({ ...EVENT, title: 'Renamed science project', start: '2027-01-02' }, NOW, ORIGIN)).properties.UID).toBe(properties.UID);
    expect(parseFile(buildCalendarFile({ ...EVENT, id: 'homework:43' }, NOW, ORIGIN)).properties.UID).not.toBe(properties.UID);
    expect(parseFile(buildCalendarFile(EVENT, NOW, { origin: 'https://other.example' })).properties.UID).not.toBe(properties.UID);
  });

  it('writes timed dates in UTC with no floating local timezone', () => {
    const { properties } = parseFile(buildCalendarFile({ ...EVENT, start: '2026-10-11T10:00:00-07:00' }, NOW, ORIGIN));
    expect(properties.DTSTART).toBe('20261011T170000Z');
    expect(properties.DTEND).toBe('20261011T173000Z');
    expect(properties['DTSTART;VALUE=DATE']).toBeUndefined();
  });

  it('escapes punctuation, backslashes and all newline styles without injecting properties', () => {
    const title = 'Paint, glue; paper \\ supplies\r\nBEGIN:VEVENT';
    const file = buildCalendarFile({ ...EVENT, title, description: 'First\rSecond\nThird\r\nFourth' }, NOW, ORIGIN);
    const { properties, lines } = parseFile(file);
    expect(properties.SUMMARY).toBe('Paint\\, glue\\; paper \\\\ supplies\\nBEGIN:VEVENT');
    expect(properties.DESCRIPTION).toBe('First\\nSecond\\nThird\\nFourth\\n\\nhttps://abby.example/quests?tab=study');
    expect(lines.filter((line) => line === 'BEGIN:VEVENT')).toHaveLength(1);
  });

  it('folds Unicode lines to at most 75 UTF-8 octets without breaking emoji', () => {
    const title = '🧶 café; '.repeat(30);
    const file = buildCalendarFile({ ...EVENT, title }, NOW, ORIGIN);
    expect(file).toContain('\r\n ');
    for (const line of file.split('\r\n')) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(parseFile(file).properties.SUMMARY).toBe(title.replaceAll(';', '\\;'));
    expect(file).not.toContain('�');
  });

  it('rejects missing events, titles and invalid timestamps', () => {
    expect(buildCalendarFile(null, NOW, ORIGIN)).toBeNull();
    expect(buildCalendarFile({ ...EVENT, title: '' }, NOW, ORIGIN)).toBeNull();
    expect(buildCalendarFile(EVENT, new Date('invalid'), ORIGIN)).toBeNull();
  });
});

describe('calendar download', () => {
  it('downloads an actual calendar blob with a safe filename and delayed object URL release', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout'] });
    const downloads = stubDownload();
    expect(downloadCalendarFile({ ...EVENT, title: '../../Science & Art: due?' })).toBe(true);
    expect(downloads).toEqual([{ filename: 'Science-Art-due.ics', href: 'blob:calendar-copy', attached: true }]);
    const blob = URL.createObjectURL.mock.calls[0][0];
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('text/calendar;charset=utf-8');
    expect(parseFile(await readBlob(blob)).properties['DTSTART;VALUE=DATE']).toBe('20261231');
    expect(document.querySelector('a[download]')).toBeNull();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(59_999);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:calendar-copy');
  });

  it('does not create a blob for an invalid date', () => {
    stubDownload();
    expect(downloadCalendarFile({ ...EVENT, start: undefined })).toBe(false);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
