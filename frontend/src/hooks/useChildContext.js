import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getChildren } from '../api';
import { getToken } from '../api/client';
import { normalizeList } from '../utils/api';
import { useRole } from './useRole';

// URLs carry only a child ID. It is usable only after the current account's
// family roster verifies it; credentials and child data never enter the URL.
// Remember only the selected ID per parent/family; verify it on every mount.
export default function useChildContext() {
  const { user, isParent } = useRole();
  const [params, setParams] = useSearchParams();
  const accountScope = `${user?.id}:${user?.role}:${user?.family?.id ?? ''}:${getToken()}`;
  const [state, setState] = useState(null);
  const [revision, setRevision] = useState(0);
  const current = state?.scope === accountScope ? state : null;
  useEffect(() => {
    if (!isParent || !user?.id) return undefined;
    let cancelled = false;
    getChildren().then((response) => {
      if (!cancelled) setState({ scope: accountScope, children: normalizeList(response), error: null });
    }).catch((error) => {
      if (!cancelled) setState({ scope: accountScope, children: null, error: error.message });
    });
    return () => { cancelled = true; };
  }, [accountScope, isParent, user?.id, revision]);
  const children = current?.children ?? null;
  const storageKey = `abby:child-context:${user?.family?.id ?? ''}:${user?.id}`;
  let rememberedId = null;
  try { rememberedId = localStorage.getItem(storageKey); } catch { /* Storage is optional. */ }
  const requestedId = params.get('child') || rememberedId;
  const selectedChild = children?.find((child) => String(child.id) === requestedId) ?? children?.[0] ?? null;
  useEffect(() => {
    if (!isParent || !selectedChild) return;
    try { localStorage.setItem(storageKey, String(selectedChild.id)); } catch { /* Storage is optional. */ }
  }, [isParent, selectedChild, storageKey]);
  const selectChild = (id) => {
    const child = children?.find((candidate) => String(candidate.id) === String(id));
    if (!child) return;
    const next = new URLSearchParams(params);
    next.set('child', String(child.id));
    setParams(next, { replace: true });
  };
  return {
    user, isParent, children, selectedChild, selectChild,
    targetUserId: isParent ? selectedChild?.id ?? null : user?.id,
    scope: accountScope,
    loading: isParent && !current,
    error: current?.error ?? null,
    reload: () => setRevision((value) => value + 1),
  };
}
