import { Compass, Sprout, Sparkles, Flower2, Eye, Heart } from 'lucide-react';

const GLYPHS = {
  'compass-rose': Compass, 'dragon-crest': Sprout, 'flourish-corner': Sparkles,
  'rune-orb': Flower2, 'sheikah-eye': Eye, 'wax-seal': Heart,
};

// Legacy glyph props remain compatible; the marks now match the shared icons.
export default function DeckleDivider({ glyph = 'compass-rose', label, className = '' }) {
  const Glyph = GLYPHS[glyph] || Compass;
  return (
    <div className={`relative flex items-center justify-center my-6 ${className}`} role="separator" aria-hidden={!label}>
      <div className="flex-1 h-px bg-ink-page-shadow" />
      <div className="px-3 flex items-center gap-2 text-sheikah-teal">
        <Glyph size={18} aria-hidden="true" />
        {label && <span className="font-body text-caption text-ink-secondary">{label}</span>}
      </div>
      <div className="flex-1 h-px bg-ink-page-shadow" />
    </div>
  );
}
