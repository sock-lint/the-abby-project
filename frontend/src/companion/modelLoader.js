import { useLoader } from '@react-three/fiber';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export function resetModels(failedUrls) {
  // Preserve the bounded resolved cache across context loss/remounts. Clearing
  // only rejected loads avoids allocating another copy of healthy GPU assets.
  for (const url of failedUrls) useLoader.clear(GLTFLoader, url);
}
