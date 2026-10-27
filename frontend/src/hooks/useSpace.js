import { useContext } from 'react';
import { SpaceContext } from '../providers/spaceContext';
import { useRole } from './useRole';

export function useSpace() {
  const context = useContext(SpaceContext);
  const { user } = useRole();
  return context ?? fallbackSpace(user);
}

// Header/navigation primitives also work with an explicit user outside the
// application providers (the design library and isolated component checks).
export function useSpaceForUser(user) {
  const context = useContext(SpaceContext);
  return context ?? fallbackSpace(user);
}

function fallbackSpace(user) {
  const isParentAccount = user?.role === 'parent';
  return {
    space: isParentAccount ? 'family' : 'personal',
    isParentAccount,
    isPersonalSpace: !isParentAccount,
    isFamilySpace: isParentAccount,
    switchSpace: () => false,
    switchBlocked: false,
  };
}
