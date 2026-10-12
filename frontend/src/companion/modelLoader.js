import { useLoader } from '@react-three/fiber';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export function resetModels(failedUrls, creatureUrls = []) {
  // Preserve the bounded resolved cache across context loss/remounts. Clearing
  // only rejected loads avoids allocating another copy of healthy GPU assets.
  for (const url of failedUrls) useLoader.clear(GLTFLoader, url);
  // Creature playback loads its matched rigs as a single suspense entry.
  // The grouped rejection is keyed by that exact ordered URL list.
  if (creatureUrls.some((url) => failedUrls.includes(url))) {
    useLoader.clear(GLTFLoader, creatureUrls);
  }
}
