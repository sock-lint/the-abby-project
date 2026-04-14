import { motion } from 'framer-motion';
import { Package, Gem } from 'lucide-react';
import { getInventory } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import { normalizeList } from '../utils/api';
import { RARITY_PILL_COLORS } from '../constants/colors';

const TYPE_LABELS = {
  egg: 'Pet Eggs',
  potion: 'Hatching Potions',
  food: 'Pet Food',
  cosmetic_frame: 'Avatar Frames',
  cosmetic_title: 'Titles',
  cosmetic_theme: 'Themes',
  cosmetic_pet_accessory: 'Pet Accessories',
  quest_scroll: 'Quest Scrolls',
  coin_pouch: 'Coin Pouches',
};

export default function Inventory() {
  const { data, loading } = useApi(getInventory);
  const items = normalizeList(data);

  if (loading) return <Loader />;

  // Group by item type
  const grouped = {};
  for (const entry of items) {
    const type = entry.item.item_type;
    if (!grouped[type]) grouped[type] = [];
    grouped[type].push(entry);
  }

  const types = Object.keys(grouped);

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
        <Package size={22} /> Inventory
      </h1>

      {types.length === 0 ? (
        <EmptyState>No items yet. Complete tasks to earn drops!</EmptyState>
      ) : (
        types.map((type) => (
          <div key={type}>
            <h2 className="font-heading text-lg font-bold mb-3">
              {TYPE_LABELS[type] || type}
            </h2>
            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {grouped[type].map((entry) => (
                <motion.div
                  key={entry.id}
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                >
                  <Card className="text-center p-3">
                    <div className="text-3xl mb-1">{entry.item.icon}</div>
                    <div className="text-xs font-medium truncate">{entry.item.name}</div>
                    <div className="flex items-center justify-center gap-1 mt-1">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${RARITY_PILL_COLORS[entry.item.rarity] || ''}`}>
                        {entry.item.rarity_display}
                      </span>
                    </div>
                    {entry.quantity > 1 && (
                      <div className="text-xs text-forge-text-dim mt-1">x{entry.quantity}</div>
                    )}
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
