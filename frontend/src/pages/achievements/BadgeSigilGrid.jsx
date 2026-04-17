import { motion } from 'framer-motion';
import EmptyState from '../../components/EmptyState';
import BadgeSigil from './BadgeSigil';

const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, epic: 3, legendary: 4 };

/**
 * BadgeSigilGrid — responsive grid of wax-seal sigils. 2-col at 375px so
 * each sigil lands above the 120px readability floor; climbs to 5-col on
 * desktop. Sort order (earned first, then by rarity + name) matches the
 * legacy BadgeCollection contract so existing expectations survive.
 */
export default function BadgeSigilGrid({ allBadges, earnedBadges, onSelect }) {
  if (!allBadges?.length) {
    return <EmptyState>No badges have been forged yet.</EmptyState>;
  }

  const earnedIds = new Set(earnedBadges.map((ub) => ub.badge.id));
  const earnedMap = Object.fromEntries(
    earnedBadges.map((ub) => [ub.badge.id, ub]),
  );

  const sorted = allBadges
    .map((badge) => ({
      badge,
      earned: earnedIds.has(badge.id),
      earnedAt: earnedMap[badge.id]?.earned_at || null,
    }))
    .sort((a, b) => {
      if (a.earned && !b.earned) return -1;
      if (!a.earned && b.earned) return 1;
      if (a.earned && b.earned) return new Date(b.earnedAt) - new Date(a.earnedAt);
      return (
        (RARITY_ORDER[a.badge.rarity] - RARITY_ORDER[b.badge.rarity]) ||
        a.badge.name.localeCompare(b.badge.name)
      );
    });

  return (
    <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 md:gap-4 list-none p-0 m-0">
      {sorted.map((item, i) => (
        <motion.li
          key={item.badge.id}
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: Math.min(i, 11) * 0.03, duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
        >
          <BadgeSigil
            badge={item.badge}
            earned={item.earned}
            earnedAt={item.earnedAt}
            onSelect={onSelect}
          />
        </motion.li>
      ))}
    </ul>
  );
}
