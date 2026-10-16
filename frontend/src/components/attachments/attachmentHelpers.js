import { fieldErrors } from '../../utils/api';

export function formatFileSize(bytes) {
  if (bytes < 1000) return `${bytes} ${bytes === 1 ? 'byte' : 'bytes'}`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

// Keep server file validation next to the chooser without losing other errors.
export function attachmentErrorMessages(error, field, fallback) {
  const fields = fieldErrors(error);
  const fileError = fields[field] || '';
  const hasOtherFields = Object.keys(fields).some((key) => key !== field);
  const body = error?.response;
  const hasGeneralError = body?.detail || body?.error || body?.non_field_errors;
  return {
    fileError,
    message: fileError && !hasOtherFields && !hasGeneralError ? '' : error?.message || fallback,
  };
}
