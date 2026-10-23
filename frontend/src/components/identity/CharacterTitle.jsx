import CatalogIcon from '../rpg/CatalogIcon';
import './identity.css';

/** A saved title keeps its authored text and icon wherever identity appears. */
export default function CharacterTitle({ title, compact = false, className = '' }) {
  const text = title?.metadata?.text || title?.metadata?.title_text || title?.name;
  if (!text) return null;
  const hasIcon = title.catalog_icon || title.sprite_key || title.icon;

  return <span className={`character-title ${className}`}
    role={compact ? 'img' : undefined} aria-label={compact ? `Title: ${text}` : undefined}
    title={compact ? text : undefined} data-identity-icon={compact ? 'title' : undefined}>
    {(hasIcon || compact) && <span className="character-title__icon" aria-hidden="true">
      <CatalogIcon assetId={title.catalog_icon} spriteKey={title.sprite_key} icon={title.icon} size={18} alt="" />
    </span>}
    {!compact && <span className="character-title__text">{text}</span>}
  </span>;
}
