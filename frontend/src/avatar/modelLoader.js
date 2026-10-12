import { useLoader } from '@react-three/fiber';
import { TextureLoader } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export function resetAvatarAssets(appearance, failedUrls) {
  if (!appearance) return;
  if (failedUrls.includes(appearance.url)) useLoader.clear(GLTFLoader, appearance.url);
  const textures = Object.values(appearance.textures);
  // useLoader caches an array load under the full array, not each URL.
  if (textures.some((url) => failedUrls.includes(url))) useLoader.clear(TextureLoader, textures);
}
