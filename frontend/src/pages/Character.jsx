import { useState } from 'react';
import { motion } from 'framer-motion';
import { Crown, Palette, Sparkles, X, Check, Flame, Star } from 'lucide-react';
import {
  getCharacterProfile, getCosmetics, equipCosmetic, unequipCosmetic,
} from '../api';
import { useApi } from '../hooks/useApi';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import ParchmentCard from '../components/journal/ParchmentCard';
import DeckleDivider from '../components/journal/DeckleDivider';
import RuneBadge from '../components/journal/RuneBadge';
import StreakFlame from '../components/journal/StreakFlame';
import { RARITY_RING_COLORS } from '../constants/colors';

const SLOT_ICONS = {
  active_frame: Palette,
  active_title: Crown,
  active_theme: Palette,
  active_pet_accessory: Sparkles,
};

const SLOT_LABELS = {
  active_frame: { label: 'Avatar Frame', kicker: 'a border of renown' },
  active_title: { label: 'Title', kicker: 'hard-won honorific' },
  active_theme: { label: 'Journal Cover', kicker: 'the page aesthetic' },
  active_pet_accessory: { label: 'Pet Accessory', kicker: 'a saddle, a sash' },
};

export default function Character() {
  const { data: profile, loading: loadingProfile, reload: reloadProfile } = useApi(getCharacterProfile);
  const { data: cosmetics, loading: loadingCosmetics, reload: reloadCosmetics } = useApi(getCosmetics);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(null);

  if (loadingProfile || loadingCosmetics) return <Loader />;
  if (!profile) return <EmptyState>Unable to load sigil.</EmptyState>;

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

  const frameColor = profile.active_frame?.metadata?.border_color || 'var(--color-sheikah-teal-deep)';
  const titleText = profile.active_title?.metadata?.text || profile.active_title?.name;
  const initial = (profile.display_name || profile.username || '?')[0].toUpperCase();

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the sigil · who you are
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Sigil
        </h1>
      </header>

      <ErrorAlert message={error} />

      {/* Hero profile card */}
      <ParchmentCard flourish tone="bright" className="text-center py-8">
        <div
          className="w-28 h-28 mx-auto rounded-full bg-sheikah-teal/20 flex items-center justify-center font-display text-5xl text-sheikah-teal-deep"
          style={profile.active_frame ? { border: `4px solid ${frameColor}`, padding: '3px' } : { border: '2px solid var(--color-ink-page-shadow)' }}
        >
          {initial}
        </div>
        <div className="mt-3 font-display italic text-2xl text-ink-primary">
          {profile.display_name || profile.username}
        </div>
        {titleText && (
          <div className="font-script text-gold-leaf text-lg flex items-center justify-center gap-1 mt-0.5">
            <Crown size={14} className="text-gold-leaf" /> {titleText}
          </div>
        )}
        <div className="mt-2">
          <RuneBadge tone="teal" size="md">level {profile.level}</RuneBadge>
        </div>

        <div className="grid grid-cols-3 gap-3 mt-5 max-w-md mx-auto">
          <div className="rounded-lg bg-ink-page/60 border border-ink-page-shadow py-2">
            <Flame size={18} className="mx-auto text-ember-deep" />
            <div className="font-rune text-xl font-bold text-ink-primary">
              {profile.login_streak}
            </div>
            <div className="font-script text-xs text-ink-whisper">streak</div>
          </div>
          <div className="rounded-lg bg-ink-page/60 border border-ink-page-shadow py-2">
            <Star size={18} className="mx-auto text-gold-leaf" />
            <div className="font-rune text-xl font-bold text-ink-primary">
              {profile.perfect_days_count}
            </div>
            <div className="font-script text-xs text-ink-whisper">perfect days</div>
          </div>
          <div className="rounded-lg bg-ink-page/60 border border-ink-page-shadow py-2">
            <Flame size={18} className="mx-auto text-royal" />
            <div className="font-rune text-xl font-bold text-ink-primary">
              {profile.longest_login_streak}
            </div>
            <div className="font-script text-xs text-ink-whisper">best streak</div>
          </div>
        </div>
      </ParchmentCard>

      {/* Cosmetic slots */}
      {Object.entries(SLOT_LABELS).map(([slot, meta], idx) => {
        const owned = cosmetics?.[slot] || [];
        const active = profile[slot];
        const SlotIcon = SLOT_ICONS[slot];

        return (
          <section key={slot}>
            {idx > 0 && <DeckleDivider glyph="flourish-corner" />}
            <div className="flex items-center gap-2 mb-3">
              <SlotIcon size={16} className="text-sheikah-teal-deep" />
              <div className="flex-1">
                <div className="font-script text-xs text-ink-whisper">{meta.kicker}</div>
                <h2 className="font-display text-lg text-ink-primary leading-tight">
                  {meta.label}
                </h2>
              </div>
              {active && (
                <button
                  type="button"
                  onClick={() => handleUnequip(slot)}
                  disabled={working === slot}
                  className="font-script text-xs text-ember-deep hover:text-ember flex items-center gap-1 transition-colors"
                >
                  <X size={12} /> unequip
                </button>
              )}
            </div>

            {owned.length === 0 ? (
              <div className="font-script text-sm text-ink-whisper italic">
                none owned yet — earn drops from tasks
              </div>
            ) : (
              <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {owned.map((item) => {
                  const isActive = active?.id === item.id;
                  return (
                    <motion.button
                      key={item.id}
                      type="button"
                      whileHover={{ y: -2 }}
                      onClick={() => !isActive && handleEquip(item.id)}
                      className={`text-center p-2.5 rounded-xl bg-ink-page-aged border border-ink-page-shadow transition-all
                        ${isActive
                          ? `ring-2 ring-offset-2 ring-offset-ink-page ${RARITY_RING_COLORS[item.rarity] || 'ring-sheikah-teal'}`
                          : 'hover:border-sheikah-teal/50 cursor-pointer'
                        }`}
                    >
                      <div className="text-2xl mb-0.5">{item.icon}</div>
                      <div className="font-body text-[11px] font-medium truncate">
                        {item.name}
                      </div>
                      {isActive && (
                        <div className="font-script text-[10px] text-moss flex items-center justify-center gap-0.5 mt-0.5">
                          <Check size={10} /> equipped
                        </div>
                      )}
                    </motion.button>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
