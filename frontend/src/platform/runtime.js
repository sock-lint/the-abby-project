import { Capacitor } from '@capacitor/core';

// The build flag also disables browser-only services when inspecting the
// packaged bundle in a desktop browser before installing it on a phone.
export function isNativeRuntime() {
  return import.meta.env.VITE_NATIVE_BUILD === 'true' || Capacitor.isNativePlatform();
}
