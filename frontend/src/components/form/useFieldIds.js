import { useId } from 'react';

/**
 * useFieldIds — shared id derivation for form primitives.
 *
 * Returns stable per-instance ids for the control, an optional helpText
 * region, and an optional error region — plus a pre-joined `aria-describedby`
 * value (or `undefined` when neither helpText nor error is present, so React
 * drops the attribute entirely instead of writing an empty string).
 *
 * Consumers may pass `idProp` to override the generated id (useful when a
 * parent form library has already assigned one).
 */
export default function useFieldIds({ idProp, helpText, error }) {
  const generatedId = useId();
  const id = idProp || generatedId;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;
  return { id, helpId, errorId, describedBy };
}
