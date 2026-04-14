import compassRoseUrl from '../../assets/glyphs/compass-rose.svg';
import dragonCrestUrl from '../../assets/glyphs/dragon-crest.svg';
import flourishCornerUrl from '../../assets/glyphs/flourish-corner.svg';
import runeOrbUrl from '../../assets/glyphs/rune-orb.svg';
import sheikahEyeUrl from '../../assets/glyphs/sheikah-eye.svg';
import waxSealUrl from '../../assets/glyphs/wax-seal.svg';

const GLYPH_URLS = {
  'compass-rose': compassRoseUrl,
  'dragon-crest': dragonCrestUrl,
  'flourish-corner': flourishCornerUrl,
  'rune-orb': runeOrbUrl,
  'sheikah-eye': sheikahEyeUrl,
  'wax-seal': waxSealUrl,
};

/**
 * DeckleDivider — a torn-paper section divider with an optional Sheikah
 * glyph centered in the tear. Used between sections of long pages.
 */
export default function DeckleDivider({ glyph = 'compass-rose', label, className = '' }) {
  return (
    <div
      className={`relative flex items-center justify-center my-6 ${className}`}
      role="separator"
      aria-hidden={!label}
    >
      <div className="flex-1 h-px bg-ink-page-shadow" />
      <div className="px-3 flex items-center gap-2">
        <img
          src={GLYPH_URLS[glyph] ?? GLYPH_URLS['compass-rose']}
          alt=""
          aria-hidden="true"
          className="w-6 h-6 opacity-60"
          style={{ filter: 'sepia(1) saturate(0.6) brightness(0.5)' }}
        />
        {label ? (
          <span className="font-script text-sm text-ink-whisper uppercase tracking-wider">
            {label}
          </span>
        ) : null}
      </div>
      <div className="flex-1 h-px bg-ink-page-shadow" />
    </div>
  );
}
