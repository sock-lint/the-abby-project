import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import BottomSheet from '../../components/BottomSheet';
import EmptyState from '../../components/EmptyState';
import { RARITY_COLORS, RARITY_TEXT_COLORS } from '../../constants/colors';
import { formatDate } from '../../utils/format';

const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, epic: 3, legendary: 4 };

export default function BadgeCollection({ allBadges, earnedBadges }) {
  const [selectedBadge, setSelectedBadge] = useState(null);

  const earnedBadgeIds = new Set(earnedBadges.map((ub) => ub.badge.id));
  const earnedBadgeMap = Object.fromEntries(earnedBadges.map((ub) => [ub.badge.id, ub]));

  const sortedBadges = allBadges
    .map((badge) => ({
      badge,
      earned: earnedBadgeIds.has(badge.id),
      earnedAt: earnedBadgeMap[badge.id]?.earned_at || null,
    }))
    .sort((a, b) => {
      if (a.earned && !b.earned) return -1;
      if (!a.earned && b.earned) return 1;
      if (a.earned && b.earned) return new Date(b.earnedAt) - new Date(a.earnedAt);
      return (RARITY_ORDER[a.badge.rarity] - RARITY_ORDER[b.badge.rarity])
        || a.badge.name.localeCompare(b.badge.name);
    });

  return (
    <div>
      <h2 className="font-display text-lg font-bold mb-3">
        Badges ({earnedBadgeIds.size}/{allBadges.length})
      </h2>
      {allBadges.length === 0 ? (
        <EmptyState>No badges have been created yet.</EmptyState>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
          {sortedBadges.map((item, i) => (
            <motion.div
              key={item.badge.id}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: i * 0.03 }}
            >
              <div
                className={`rounded-xl p-4 text-center border cursor-pointer transition-colors ${
                  item.earned
                    ? RARITY_COLORS[item.badge.rarity]
                    : 'bg-ink-page-aged/50 border-ink-page-shadow opacity-40 grayscale'
                }`}
                onClick={() => setSelectedBadge(item)}
              >
                <div className="text-3xl mb-1">{item.badge.icon || '🔒'}</div>
                <div className="text-xs font-medium leading-tight">{item.badge.name}</div>
                <div className={`text-micro capitalize ${
                  item.earned ? RARITY_TEXT_COLORS[item.badge.rarity] : 'text-ink-whisper'
                }`}>
                  {item.badge.rarity}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {selectedBadge && (
          <BottomSheet
            title={selectedBadge.badge.name}
            onClose={() => setSelectedBadge(null)}
          >
            <div className="text-center">
              <div className="text-5xl mb-3">{selectedBadge.badge.icon}</div>
              <div className={`text-sm capitalize font-medium mb-2 ${RARITY_TEXT_COLORS[selectedBadge.badge.rarity]}`}>
                {selectedBadge.badge.rarity}
              </div>
              <p className="text-sm text-ink-whisper mb-3">
                {selectedBadge.badge.description}
              </p>
              {selectedBadge.badge.xp_bonus > 0 && (
                <div className="text-xs text-sheikah-teal-deep">
                  +{selectedBadge.badge.xp_bonus} XP bonus
                </div>
              )}
              {selectedBadge.earned ? (
                <div className="mt-3 text-xs text-ink-whisper">
                  Earned {formatDate(selectedBadge.earnedAt)}
                </div>
              ) : (
                <div className="mt-3 text-xs text-ink-whisper italic">
                  Not yet earned
                </div>
              )}
            </div>
          </BottomSheet>
        )}
      </AnimatePresence>
    </div>
  );
}
