/**
 * Downscale an image File on the client before upload so phones aren't
 * pushing 8–12MB originals over cellular. Skips files that are already small
 * or not images. Returns a new File (always JPEG when downscaled) or the
 * original file unchanged.
 */
export async function downscaleImage(file, { maxDim = 1600, quality = 0.85 } = {}) {
  if (!file || !file.type || !file.type.startsWith('image/')) return file;
  // If the file is already small, skip the round-trip.
  if (file.size < 500 * 1024) return file;

  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    // Browsers that can't decode (e.g., HEIC on older Chrome) — upload as-is.
    return file;
  }

  const { width, height } = bitmap;
  if (width <= maxDim && height <= maxDim) {
    bitmap.close?.();
    return file;
  }

  const scale = maxDim / Math.max(width, height);
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', quality)
  );
  if (!blob) return file;

  const name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
  return new File([blob], name, { type: 'image/jpeg' });
}
