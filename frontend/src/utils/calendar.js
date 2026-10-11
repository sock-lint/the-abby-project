const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|([+-])(\d{2}):(\d{2}))$/;
const TAB_ROUTES = {
  '/quests': ['study', 'forge', 'trials', 'duties', 'ventures', 'rituals', 'movement'],
  '/bestiary': ['mounts', 'companions', 'hatchery', 'codex'],
  '/atlas': ['skills', 'badges', 'sketchbook', 'yearbook'],
};

function validDay(value) {
  if (typeof value !== 'string' || !DAY_PATTERN.test(value) || value.startsWith('0000-')) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function parseTime(value) {
  if (typeof value !== 'string') return null;
  const parts = value.match(TIME_PATTERN);
  if (!parts || !validDay(parts[1]) || Number(parts[2]) > 23 || Number(parts[3]) > 59
    || Number(parts[4] || 0) > 59 || Number(parts[7] || 0) > 23 || Number(parts[8] || 0) > 59) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.getUTCFullYear() >= 1 && date.getUTCFullYear() <= 9999 ? date : null;
}

function calendarTime(date) {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

function currentOrigin(origin) {
  try {
    const url = new URL(origin ?? window.location.origin);
    return ['https:', 'http:'].includes(url.protocol) ? url.origin : null;
  } catch {
    return null;
  }
}

// Only a caller-authored route and known navigation tabs leave the app.
// Never export the current URL, auth state, arbitrary query strings or hashes.
function appLink(path, origin) {
  if (!origin || typeof path !== 'string') return '';
  const route = path.split(/[?#]/)[0];
  if (!/^\/(?:[a-zA-Z0-9_-]+\/?)*$/.test(route)) return '';
  const url = new URL(path, origin);
  const tab = url.searchParams.get('tab');
  const query = TAB_ROUTES[route]?.includes(tab) ? `?tab=${tab}` : '';
  return `${origin}${route}${query}`;
}

function normalizeEvent(event, options = {}) {
  if (!event || typeof event.title !== 'string' || !event.title.trim()) return null;
  let start;
  let end;
  const allDay = validDay(event.start);
  if (allDay) {
    const followingDay = new Date(`${event.start}T00:00:00Z`);
    followingDay.setUTCDate(followingDay.getUTCDate() + 1);
    const endDay = event.end ?? followingDay.toISOString().slice(0, 10);
    if (!validDay(endDay) || endDay <= event.start) return null;
    start = event.start.replaceAll('-', '');
    end = endDay.replaceAll('-', '');
  } else {
    const startTime = parseTime(event.start);
    if (!startTime) return null;
    const endTime = event.end == null ? new Date(startTime.getTime() + 30 * 60 * 1000) : parseTime(event.end);
    if (!endTime || endTime.getUTCFullYear() > 9999 || endTime <= startTime) return null;
    start = calendarTime(startTime);
    end = calendarTime(endTime);
    if (end <= start) return null;
  }
  const origin = currentOrigin(options.origin);
  const link = appLink(event.path, origin);
  const description = [event.description, link].filter(Boolean).join('\n\n');
  const id = event.id ?? `${event.title}:${event.start}`;
  return { allDay, start, end, title: event.title, description, link,
    uid: `abby-${encodeURIComponent(origin || 'abby')}-${encodeURIComponent(id)}@the-abby-project` };
}

/** One-time event template, per Google's documented pre-filled event link.
 * https://developers.google.com/workspace/calendar/api/concepts/inviting-attendees-to-events
 * Date-only ranges keep calendar dates; timed ranges are UTC instants.
 */
export function buildGoogleCalendarUrl(event, options) {
  const normalized = normalizeEvent(event, options);
  if (!normalized) return null;
  const url = new URL('https://calendar.google.com/calendar/r/eventedit');
  url.searchParams.set('action', 'TEMPLATE');
  url.searchParams.set('text', normalized.title);
  url.searchParams.set('dates', `${normalized.start}/${normalized.end}`);
  if (normalized.description) url.searchParams.set('details', normalized.description);
  return url.href;
}

function escapeText(value) {
  return String(value).replaceAll('\\', '\\\\').replace(/\r\n|\r|\n/g, '\\n')
    .replaceAll(';', '\\;').replaceAll(',', '\\,');
}

// RFC 5545 section 3.1: fold at 75 UTF-8 octets without splitting a code point.
function foldLine(line) {
  const encoder = new TextEncoder();
  let result = '';
  let octets = 0;
  for (const character of line) {
    const length = encoder.encode(character).length;
    if (octets + length > 75) {
      result += '\r\n ';
      octets = 1;
    }
    result += character;
    octets += length;
  }
  return result;
}

/** Standalone RFC 5545 event for Apple Calendar's .ics import.
 * https://www.rfc-editor.org/rfc/rfc5545
 * `end` is exclusive for all-day events; a missing timed end is 30 minutes.
 * Invalid events return null. `options.origin` is an optional testing seam.
 */
export function buildCalendarFile(event, now = new Date(), options) {
  const normalized = normalizeEvent(event, options);
  const timestamp = new Date(now);
  if (!normalized || !Number.isFinite(timestamp.getTime())) return null;
  const dateType = normalized.allDay ? ';VALUE=DATE' : '';
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//The Abby Project//Calendar Export//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${escapeText(normalized.uid)}`,
    `DTSTAMP:${calendarTime(timestamp)}`,
    `DTSTART${dateType}:${normalized.start}`,
    `DTEND${dateType}:${normalized.end}`,
    `SUMMARY:${escapeText(normalized.title)}`,
  ];
  if (normalized.description) lines.push(`DESCRIPTION:${escapeText(normalized.description)}`);
  if (normalized.link) lines.push(`URL:${normalized.link}`);
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return `${lines.map(foldLine).join('\r\n')}\r\n`;
}

/** Start a browser download, retaining the blob URL long enough for Safari.
 * Returns false for invalid input; browser download errors propagate to the UI.
 */
export function downloadCalendarFile(event) {
  const content = buildCalendarFile(event);
  if (!content) return false;
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  const name = event.title.normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  anchor.download = `${name || 'calendar-event'}.ics`;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60 * 1000);
  }
  return true;
}
