import { useAuth } from './useApi';

/**
 * Convenience wrapper around useAuth() for pages that only need the current
 * user's role. Replaces the repeated ``const isParent = user?.role === 'parent'``
 * pattern across pages.
 */
export function useRole() {
  const { user } = useAuth();
  return {
    user,
    role: user?.role,
    isParent: user?.role === 'parent',
    isChild: user?.role === 'child',
  };
}
