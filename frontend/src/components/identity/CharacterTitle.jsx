import CatalogIcon from '../rpg/CatalogIcon';
import './identity.css';

/** A saved title keeps its authored text and icon wherever identity appears. */
export default function CharacterTitle({ title, className = '' }) {
  const text = title?.metadata?.text || title?.metadata?.title_text || title?.name;
  if (!text) return null;
  const hasIcon = title.catalog_icon || title.sprite_key || title.icon;

  return <span className={`character-title ${className}`}>
    {hasIcon && <span className="character-title__icon" aria-hidden="true">
      <CatalogIcon assetId={title.catalog_icon} spriteKey={title.sprite_key} icon={title.icon} size={18} alt="" />
    </span>}
    <span className="character-title__text">{text}</span>
  </span>;
}
