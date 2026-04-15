// Auto-registers every PNG in this directory at build time and exports a
// slug → URL map. New sprites added by `python scripts/slice_rpg_sprites.py`
// are picked up automatically — no manual import needed.
//
// Vite's `import.meta.glob` with `eager: true` resolves URLs at build time,
// so the bundle includes hashed filenames for cache-busting.

const modules = import.meta.glob('./*.png', { eager: true, import: 'default' });

export const rewardIconMap = Object.fromEntries(
  Object.entries(modules).map(([path, url]) => {
    const slug = path.replace(/^\.\//, '').replace(/\.png$/, '');
    return [slug, url];
  }),
);

export function getSpriteUrl(spriteKey) {
  if (!spriteKey) return null;
  return rewardIconMap[spriteKey] ?? null;
}
