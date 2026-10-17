import { RARITY_PILL_COLORS } from '../../constants/colors';

/** Cover-aware rarity labels use one readable caption size in every badge view. */
export default function BadgeRarity({ rarity = 'common', quiet = false }) {
  return <span data-badge-rarity={rarity}
    className={`inline-flex max-w-full items-center rounded-full px-2 py-0.5 font-body text-caption font-semibold break-words [overflow-wrap:anywhere] ${quiet ? 'bg-ink-page-shadow/20 text-ink-secondary' : RARITY_PILL_COLORS[rarity] || RARITY_PILL_COLORS.common}`}>
    {rarity}
  </span>;
}
