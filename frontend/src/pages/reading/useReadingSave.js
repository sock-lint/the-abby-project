import { useEffect, useRef, useState } from 'react';
import { getToken } from '../../api/client';
import { fieldErrors } from '../../utils/api';
import { friendlyErrorMessage } from '../../hooks/useApi';
import { createRequestId } from '../../utils/requestId';

// An interrupted POST may already have saved. Freeze its exact payload and
// idempotency key until a confirmed receipt or definite validation rejection.
// Drafts and reflections stay in memory and never enter device storage.
export default function useReadingSave({ create, update, existing, onSaved, credential }) {
  const mounted = useRef(false);
  const request = useRef(null);
  const inFlight = useRef(false);
  const [saving, setSaving] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const current = () => mounted.current && credential === getToken();
  const save = async (payload) => {
    if (inFlight.current || !current()) return;
    inFlight.current = true;
    if (!request.current) request.current = existing ? payload : { ...payload, client_request_id: createRequestId() };
    setSaving(true);
    setError('');
    setErrors({});
    try {
      const receipt = existing ? await update(existing.id, request.current) : await create(request.current);
      if (current()) onSaved(receipt);
    } catch (err) {
      if (!current()) return;
      const rejected = err.status >= 400 && err.status < 500;
      if (rejected) request.current = null;
      setUncertain(!rejected);
      const fields = fieldErrors(err);
      setErrors(fields);
      setError(Object.keys(fields).length ? 'Check the highlighted fields.' : err.response?.non_field_errors?.[0] || friendlyErrorMessage(err));
    } finally {
      inFlight.current = false;
      if (current()) setSaving(false);
    }
  };
  return { save, saving, uncertain, error, errors };
}
