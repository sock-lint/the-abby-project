import { getConsoleFunction, setConsoleFunction } from 'three';

const CLOCK_DEPRECATION = 'THREE.Clock: This module has been deprecated. Please use THREE.Timer instead.';

// Stable R3F 9 creates a Clock before onCreated, and Timer is not a drop-in
// replacement for its clock API. Remove this filter when stable R3F migrates.
// https://github.com/pmndrs/react-three-fiber/blob/v9.8.2/packages/fiber/src/core/store.ts
export function installThreeConsoleFilter() {
  const previous = getConsoleFunction();
  const filtered = (type, message, ...params) => {
    if (type === 'warn' && message === CLOCK_DEPRECATION && params.length === 0) return;
    if (previous) {
      previous(type, message, ...params);
      return;
    }
    // Preserve Three's native formatting for shader/TSL diagnostic stacks.
    const stack = params[0];
    const args = (type === 'warn' || type === 'error') && stack?.isStackTrace
      ? [stack.getError(message)] : [message, ...params];
    // eslint-disable-next-line no-console -- Forward the original Three log level.
    console[type](...args);
  };
  setConsoleFunction(filtered);
  return () => {
    if (getConsoleFunction() === filtered) setConsoleFunction(previous);
  };
}

const restore = installThreeConsoleFilter();
if (import.meta.hot) import.meta.hot.dispose(restore);
