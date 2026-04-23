import RpgSprite from '../../components/rpg/RpgSprite';
import { RARITY_COLORS, RARITY_TEXT_COLORS } from '../../constants/colors';

export default function CatalogCard({
  rarity, icon, spriteKey, fallbackSpriteKey, name, subtitle, onClick,
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl p-3 text-center border cursor-pointer transition-transform hover:-translate-y-0.5 ${
        RARITY_COLORS[rarity] || 'border-ink-page-shadow bg-ink-page-aged/50'
      }`}
    >
      <div className="flex items-center justify-center h-12 mb-1">
        <RpgSprite
          spriteKey={spriteKey}
          fallbackSpriteKey={fallbackSpriteKey}
          icon={icon}
          size={40}
          alt={name}
        />
      </div>
      <div className="text-xs font-medium leading-tight text-ink-primary line-clamp-2">{name}</div>
      {subtitle && (
        <div className={`text-micro mt-1 capitalize ${RARITY_TEXT_COLORS[rarity] || 'text-ink-whisper'}`}>
          {subtitle}
        </div>
      )}
    </button>
  );
}
