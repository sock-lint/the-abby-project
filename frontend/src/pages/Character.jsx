import { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Crown, Palette, Sparkles, X, Check, Flame, Star } from 'lucide-react';
import {
  getCharacterProfile, getCosmetics, equipCosmetic, unequipCosmetic,
} from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';

const SLOT_ICONS = {
  active_frame: Palette,
  active_title: Crown,
  active_theme: Palette,
  active_pet_accessory: Sparkles,
};

const SLOT_LABELS = {
  active_frame: 'Avatar Frame',
  active_title: 'Title',
  active_theme: 'Dashboard Theme',
  active_pet_accessory: 'Pet Accessory',
};

const RARITY_RING = {
  common: 'ring-gray-400',
  uncommon: 'ring-green-400',
  rare: 'ring-blue-400',
  epic: 'ring-purple-400',
  legendary: 'ring-amber-400',
};

export default function Character() {
  const { data: profile, loading: loadingProfile, reload: reloadProfile } = useApi(getCharacterProfile);
  const { data: cosmetics, loading: loadingCosmetics, reload: reloadCosmetics } = useApi(getCosmetics);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(null);

  if (loadingProfile || loadingCosmetics) return <Loader />;

  const refresh = () => { reloadProfile(); reloadCosmetics(); };

  const handleEquip = async (itemId) => {
    setWorking(itemId);
    setError('');
    try {
      await equipCosmetic(itemId);
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  const handleUnequip = async (slot) => {
    setWorking(slot);
    setError('');
    try {
      await unequipCosmetic(slot);
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  if (!profile) return <EmptyState>Unable to load profile.</EmptyState>;

  const frameColor = profile.active_frame?.metadata?.border_color || '#D97706';
  const titleText = profile.active_title?.metadata?.text || profile.active_title?.name;
  const initial = (profile.display_name || profile.username || '?')[0].toUpperCase();

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
        <User size={22} /> Character
      </h1>

      <ErrorAlert message={error} />

      {/* Hero profile card */}
      <Card className="text-center">
        <div
          className="w-24 h-24 mx-auto rounded-full bg-amber-primary/20 flex items-center justify-center text-4xl font-heading font-bold"
          style={profile.active_frame ? { border: `4px solid ${frameColor}`, padding: '3px' } : {}}
        >
          {initial}
        </div>
        <div className="mt-3 font-heading text-xl font-bold">
          {profile.display_name || profile.username}
        </div>
        {titleText && (
          <div className="text-sm text-amber-highlight flex items-center justify-center gap-1 mt-1">
            <Crown size={12} /> {titleText}
          </div>
        )}
        <div className="text-sm text-forge-text-dim mt-1">Level {profile.level}</div>

        <div className="grid grid-cols-3 gap-3 mt-4 text-xs">
          <div>
            <Flame size={16} className="mx-auto text-orange-400" />
            <div className="font-heading text-lg font-bold">{profile.login_streak}</div>
            <div className="text-forge-text-dim">Streak</div>
          </div>
          <div>
            <Star size={16} className="mx-auto text-amber-highlight" />
            <div className="font-heading text-lg font-bold">{profile.perfect_days_count}</div>
            <div className="text-forge-text-dim">Perfect Days</div>
          </div>
          <div>
            <Flame size={16} className="mx-auto text-red-400" />
            <div className="font-heading text-lg font-bold">{profile.longest_login_streak}</div>
            <div className="text-forge-text-dim">Best Streak</div>
          </div>
        </div>
      </Card>

      {/* Cosmetic slots */}
      {Object.keys(SLOT_LABELS).map((slot) => {
        const owned = cosmetics?.[slot] || [];
        const active = profile[slot];
        const SlotIcon = SLOT_ICONS[slot];

        return (
          <div key={slot}>
            <h2 className="font-heading text-sm font-bold mb-2 flex items-center gap-1.5">
              <SlotIcon size={14} /> {SLOT_LABELS[slot]}
              {active && (
                <button
                  onClick={() => handleUnequip(slot)}
                  disabled={working === slot}
                  className="ml-auto text-[10px] text-red-400 flex items-center gap-0.5 hover:text-red-300"
                >
                  <X size={10} /> Unequip
                </button>
              )}
            </h2>

            {owned.length === 0 ? (
              <div className="text-xs text-forge-text-dim">None owned. Earn drops from tasks!</div>
            ) : (
              <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                {owned.map((item) => {
                  const isActive = active?.id === item.id;
                  return (
                    <motion.div key={item.id} whileHover={{ y: -2 }}>
                      <Card className={`text-center p-2 cursor-pointer ${isActive ? `ring-2 ${RARITY_RING[item.rarity] || 'ring-amber-400'}` : ''}`}
                        onClick={() => !isActive && handleEquip(item.id)}
                      >
                        <div className="text-2xl mb-0.5">{item.icon}</div>
                        <div className="text-[10px] font-medium truncate">{item.name}</div>
                        {isActive && (
                          <div className="text-[9px] text-green-400 flex items-center justify-center gap-0.5 mt-0.5">
                            <Check size={8} /> Equipped
                          </div>
                        )}
                      </Card>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
