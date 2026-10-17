import { createRoot } from 'react-dom/client';
import '../src/index.css';
import CatalogIcon from '../src/components/rpg/CatalogIcon';
import RpgSprite from '../src/components/rpg/RpgSprite';
import { stagedCatalogRelease } from '../src/catalog/sharedCatalogIcons';
import { SpriteCatalogContext } from '../src/providers/spriteCatalog.context';
import { applyTheme } from '../src/themes';

const params = new URLSearchParams(window.location.search);
applyTheme(params.get('theme') || 'hyrule');
const staged = stagedCatalogRelease();
const representatives = [
  ['item-meat', 'Meat'], ['item-chicken-leg', 'Chicken Leg'],
  ['item-fish', 'Fish'], ['item-fish-cooked', 'Cooked Fish'],
  ['item-pouch-mega', 'Mega Hoard'], ['challenge-hoard-builder', 'Hoard Builder'],
];
const sprites = {
  legacy: { url: '/synthetic/legacy.svg', frames: 1 },
  broken: { url: '/synthetic/broken.svg', frames: 1 },
  animated: { url: '/synthetic/animated.svg', frames: 4, fps: 4 },
};
const fallback = {
  getSpriteMeta: (key) => sprites[key] || null,
  getSpriteUrl: (key) => sprites[key]?.url || null,
};

createRoot(document.getElementById('root')).render(
  <SpriteCatalogContext.Provider value={fallback}>
    <main className="bg-ink-page text-ink-primary min-h-screen p-4 space-y-6">
      <h1 className="text-2xl">Catalog icon acceptance</h1>
      <p>Private local fixture; synthetic fallbacks and no application requests.</p>
      {[32, 40, 64, 96].map((size) => (
        <section key={size} aria-label={`${size}px icons`}>
          <h2>{size} CSS pixels</h2>
          <div className="flex flex-wrap gap-4 p-3 rounded-2xl bg-ink-page-aged">
            {representatives.map(([assetId, name]) => (
              <figure key={assetId} className="text-center">
                <CatalogIcon assetId={assetId} size={size} alt={name} icon="✨" />
                <figcaption className="text-caption">{name}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
      <section aria-label="Fallback behavior" className="flex flex-wrap gap-4">
        <CatalogIcon assetId="item-meat" spriteKey="legacy" size={40} alt="Recovered legacy" icon="🍗" />
        <CatalogIcon assetId="item-meat" spriteKey="broken" fallbackSpriteKey="legacy" size={40} alt="Recovered base" icon="🍗" />
        <CatalogIcon assetId="item-meat" spriteKey="broken" size={40} alt="Recovered emoji" icon="🍗" />
        <CatalogIcon assetId="unknown-unresolved-record" spriteKey="legacy" size={40} alt="Unresolved record" icon="❓" />
        <RpgSprite spriteKey="animated" size={40} alt="Existing gameplay animation" icon="✨" />
      </section>
      {params.get('all') === '1' && <section aria-label="Every imported catalog image" className="flex flex-wrap gap-2">
        {staged?.release.assets.map((asset) => <CatalogIcon key={asset.id} assetId={asset.id} size={32} alt={asset.label} icon="❓" />)}
      </section>}
    </main>
  </SpriteCatalogContext.Provider>,
);
