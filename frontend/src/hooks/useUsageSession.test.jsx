import { act, renderHook } from '@testing-library/react';
import { AUTH_CHANGED_EVENT } from '../api/client';
import useUsageSession from './useUsageSession';
import { buildParent } from '../test/factories';

const state = vi.hoisted(() => ({ user: null }));
vi.mock('./useApi', () => ({ useAuth: () => state }));

it('fences usage state on credential, family and role replacement', () => {
  state.user = buildParent({ is_staff: true, family: { id: 1 } });
  const { result, rerender } = renderHook(() => useUsageSession());
  const original = result.current.key;
  act(() => {
    localStorage.setItem('abby_auth_token', 'replacement-test-session');
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  });
  expect(result.current.token).toBe('replacement-test-session');
  expect(result.current.key).not.toBe(original);
  const credentialKey = result.current.key;
  state.user = { ...state.user, family: { id: 2 } };
  rerender();
  expect(result.current.key).not.toBe(credentialKey);
  const familyKey = result.current.key;
  state.user = { ...state.user, role: 'child' };
  rerender();
  expect(result.current.key).not.toBe(familyKey);
});
