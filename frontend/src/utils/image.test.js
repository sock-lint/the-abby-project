import { beforeEach, describe, expect, it, vi } from 'vitest';
import { downscaleImage } from './image.js';

describe('downscaleImage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns non-image files unchanged', async () => {
    const file = new File(['hi'], 'doc.txt', { type: 'text/plain' });
    await expect(downscaleImage(file)).resolves.toBe(file);
  });

  it('returns falsy input unchanged', async () => {
    await expect(downscaleImage(null)).resolves.toBe(null);
    await expect(downscaleImage(undefined)).resolves.toBe(undefined);
  });

  it('returns files without a type unchanged', async () => {
    const broken = { name: 'x' };
    await expect(downscaleImage(broken)).resolves.toBe(broken);
  });

  it('skips small files', async () => {
    const small = new File([new Uint8Array(100)], 'tiny.jpg', {
      type: 'image/jpeg',
    });
    await expect(downscaleImage(small)).resolves.toBe(small);
  });

  it('returns original when createImageBitmap throws (e.g. HEIC)', async () => {
    const file = new File([new Uint8Array(600 * 1024)], 'photo.heic', {
      type: 'image/heic',
    });
    vi.spyOn(window, 'createImageBitmap').mockRejectedValue(new Error('unsupported'));
    await expect(downscaleImage(file)).resolves.toBe(file);
  });

  it('returns original when already under maxDim', async () => {
    const file = new File([new Uint8Array(600 * 1024)], 'photo.jpg', {
      type: 'image/jpeg',
    });
    const close = vi.fn();
    vi.spyOn(window, 'createImageBitmap').mockResolvedValue({
      width: 800,
      height: 600,
      close,
    });
    await expect(downscaleImage(file, { maxDim: 1600 })).resolves.toBe(file);
    expect(close).toHaveBeenCalled();
  });

  it('downscales large images into a new JPEG file', async () => {
    const file = new File([new Uint8Array(600 * 1024)], 'photo.png', {
      type: 'image/png',
    });
    vi.spyOn(window, 'createImageBitmap').mockResolvedValue({
      width: 4000,
      height: 3000,
      close: vi.fn(),
    });
    const result = await downscaleImage(file);
    expect(result).not.toBe(file);
    expect(result.type).toBe('image/jpeg');
    expect(result.name).toBe('photo.jpg');
  });

  it('returns original when canvas.toBlob yields null', async () => {
    const file = new File([new Uint8Array(600 * 1024)], 'photo.jpg', {
      type: 'image/jpeg',
    });
    vi.spyOn(window, 'createImageBitmap').mockResolvedValue({
      width: 4000,
      height: 3000,
      close: vi.fn(),
    });
    const toBlob = vi
      .spyOn(HTMLCanvasElement.prototype, 'toBlob')
      .mockImplementation((cb) => cb(null));
    await expect(downscaleImage(file)).resolves.toBe(file);
    expect(toBlob).toHaveBeenCalled();
  });

  it('handles bitmaps without close()', async () => {
    const file = new File([new Uint8Array(600 * 1024)], 'photo.jpg', {
      type: 'image/jpeg',
    });
    vi.spyOn(window, 'createImageBitmap').mockResolvedValue({
      width: 800,
      height: 600,
    });
    await expect(downscaleImage(file, { maxDim: 1600 })).resolves.toBe(file);
  });
});
