import PedestalImage from '../../pedestal/PedestalImage';
import ArtworkImage from '../rpg/ArtworkImage';
import { RARITY_HALO } from './mastery.constants';
import './badge-artwork.css';

const SIZE_CLASSES = { sm: 'w-14', md: 'w-16', lg: 'w-24' };
const iconSegmenter = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null;

/** Quiet collection artwork, with a gold surround for featured earned badges.
 * The actual badge icon survives absent/failed artwork. Adjacent content names
 * the badge, so this component adds no announcement or interaction of its own. */
export default function BadgeArtwork({ badge, earned = false, variant = 'tile', size }) {
  const framed = earned && variant === 'featured';
  const artworkSize = size || (variant === 'featured' ? 'lg' : 'sm');
  const iconText = badge.icon || '🏅';
  const iconLength = iconSegmenter ? [...iconSegmenter.segment(iconText)].length : Array.from(iconText).length;
  const icon = <span className={`badge-artwork__glyph ${earned ? '' : 'grayscale opacity-50'}`}>
    <ArtworkImage assetId={badge.catalog_icon} fallback={iconText} size={framed ? '37.5cqw' : '50cqw'} />
  </span>;

  return <span aria-hidden="true" data-badge-artwork={framed ? 'featured' : 'tile'}
    style={{ '--badge-icon-length': Math.max(1, iconLength) }}
    className={`badge-artwork relative isolate flex aspect-square max-w-full shrink-0 items-center justify-center ${SIZE_CLASSES[artworkSize] || SIZE_CLASSES.sm} ${framed ? '' : `rounded-2xl ${earned ? 'bg-ink-page-aged' : 'bg-ink-page-shadow/20'}`}`}>
    {framed ? <>
      <span className={`mt-frame__opening flex items-center justify-center rounded-xl border border-ink-page-shadow bg-ink-page-aged ${RARITY_HALO[badge.rarity] || RARITY_HALO.common}`}>
        {icon}
      </span>
      <PedestalImage assetId="frame-gold" className="mt-frame__art" />
    </> : icon}
  </span>;
}
