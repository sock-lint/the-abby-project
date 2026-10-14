import { it, expect } from 'vitest';
import { formatFileSize, attachmentErrorMessages } from './attachmentHelpers';
it.each([[0, '0 bytes'], [1, '1 byte'], [999, '999 bytes'], [1000, '1.0 KB'], [1_500_000, '1.5 MB']])('formats %i bytes without inventing a size limit', (bytes, display) => {
  expect(formatFileSize(bytes)).toBe(display);
});

it('shows file errors beside the chooser while preserving other server failures', () => {
  expect(attachmentErrorMessages({ response: { image: ['Unreadable image.'] }, message: 'raw response' }, 'image', 'Upload failed')).toEqual({ fileError: 'Unreadable image.', message: '' });
  expect(attachmentErrorMessages({ response: { image: ['Unreadable image.'], detail: 'The project is unavailable.' }, message: 'The project is unavailable.' }, 'image', 'Upload failed')).toEqual({ fileError: 'Unreadable image.', message: 'The project is unavailable.' });
  expect(attachmentErrorMessages({ response: { model_file: ['Empty file.'], color: ['Choose a color.'] }, message: 'Other fields need attention.' }, 'model_file', 'Request failed')).toEqual({ fileError: 'Empty file.', message: 'Other fields need attention.' });
  expect(attachmentErrorMessages(null, 'image', 'Upload failed')).toEqual({ fileError: '', message: 'Upload failed' });
});
