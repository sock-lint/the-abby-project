export function getHomeworkProofUrl(raw) {
  if (typeof raw !== 'string' || /\p{Cc}/u.test(raw)) return '';
  const value = raw.trim();
  if (!value || value.length > 2048 || /\s/.test(value) || !/^https?:\/\//i.test(value)) return '';
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return '';
    return value;
  } catch {
    return '';
  }
}
