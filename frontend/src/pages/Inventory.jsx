import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { consumeInventoryItem, getInventory, openCoinPouch } from '../api';
import { useApi } from '../hooks/useApi';
import Button from '../components/Button';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ParchmentCard from '../components/journal/ParchmentCard';
import DeckleDivider from '../components/journal/DeckleDivider';
import RuneBadge from '../components/journal/RuneBadge';
import { EggIcon } from '../components/icons/JournalIcons';
import RpgSprite from '../components/rpg/RpgSprite';
import { normalizeList } from '../utils/api';
import { RARITY_PILL_COLORS, RARITY_RING_COLORS } from '../constants/colors';
import { staggerChildren, staggerItem } from '../motion/variants';

const TYPE_COMPARTMENTS = [
  { id: 'egg', label: 'Eggs', kicker: 'dormant companions', glyph: 'dragon-crest' },
  { id: 'potion', label: 'Potions', kicker: 'elemental vials', glyph: 'rune-orb' },
  { id: 'food', label: 'Provisions', kicker: 'pet food & snacks', glyph: 'flourish-corner' },
  { id: 'cosmetic_frame', label: 'Avatar Frames', kicker: 'sigil borders', glyph: 'compass-rose' },
  { id: 'cosmetic_title', label: 'Titles', kicker: 'hard-won honorifics', glyph: 'sheikah-eye' },
  { id: 'cosmetic_theme', label: 'Journal Covers', kicker: 'aesthetic runes', glyph: 'flourish-corner' },
  { id: 'cosmetic_pet_accessory', label: 'Pet Accessories', kicker: 'saddles & adornments', glyph: 'dragon-crest' },
  { id: 'quest_scroll', label: 'Quest Scrolls', kicker: 'future adventures', glyph: 'sheikah-eye' },
  { id: 'coin_pouch', label: 'Coin Pouches', kicker: 'fortune tucked away', glyph: 'wax-seal' },
  { id: 'consumable', label: 'Consumables', kicker: 'one-use charms', glyph: 'wax-seal' },
];

export default function Inventory() {
  const navigate = useNavigate();
  const { data, loading, reload } = useApi(getInventory);
  const items = normalizeList(data);
  const [busyId, setBusyId] = useState(null);
  const [flash, setFlash] = useState(null);

  const handleAction = async (entry, action) => {
    if (action.to) {
      navigate(action.to);
      return;
    }
    if (busyId) return;
    setBusyId(entry.id);
    try {
      let result;
      if (action.id === 'open') {
        result = await openCoinPouch(entry.item.id);
      } else if (action.id === 'use') {
        result = await consumeInventoryItem(entry.item.id);
      } else {
        throw new Error('That item action is not available yet.');
      }
      setFlash({
        name: entry.item.name,
        effect: result?.effect,
        coins: result?.coins_awarded,
      });
      if (reload) await reload();
    } catch (err) {
      setFlash({ error: err?.message || 'Could not use item.' });
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <Loader />;

  const grouped = {};
  for (const entry of items) {
    const type = entry.item.item_type;
    if (!grouped[type]) grouped[type] = [];
    grouped[type].push(entry);
  }

  const populatedCompartments = TYPE_COMPARTMENTS.filter((c) => grouped[c.id]?.length);

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the satchel · all that's been gathered
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          The Satchel
        </h1>
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          drops fall from clocked work, duties, study, and quests · the ringed colour is rarity, common to legendary
        </div>
      </header>

      {flash && (
        <div
          role="status"
          className={`text-sm px-3 py-2 rounded ${
            flash.error
              ? 'bg-ember-deep/10 text-ember-deep'
              : 'bg-sheikah-teal-deep/10 text-sheikah-teal-deep'
          }`}
        >
          {flash.error
            ? flash.error
            : flash.coins
              ? `Opened ${flash.name}. You gained ${flash.coins} coins.`
              : `Used ${flash.name}. ${effectMessage(flash.effect)}`}
        </div>
      )}

      {populatedCompartments.length === 0 ? (
        <EmptyState icon={<EggIcon size={36} />}>
          <div>No items yet. Complete quests, chores, and homework to earn drops.</div>
          <div className="font-script text-sm text-ink-whisper mt-2 not-italic">
            eggs hatch pets, potions tint them, food feeds them, cosmetics dress your sigil, consumables fire one effect
          </div>
        </EmptyState>
      ) : (
        populatedCompartments.map((compartment, idx) => (
          <section key={compartment.id}>
            {idx > 0 && <DeckleDivider glyph={compartment.glyph} />}
            <div className="flex items-baseline gap-3 mb-3">
              <div>
                <div className="font-script text-sheikah-teal-deep text-sm">
                  {compartment.kicker}
                </div>
                <h2 className="font-display text-xl md:text-2xl text-ink-primary leading-tight">
                  {compartment.label}
                </h2>
              </div>
              <RuneBadge tone="ink" size="sm">
                {grouped[compartment.id].length}
              </RuneBadge>
            </div>
            <motion.div
              variants={staggerChildren}
              initial="initial"
              animate="animate"
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
            >
              {grouped[compartment.id].map((entry) => (
                <motion.div key={entry.id} variants={staggerItem}>
                  <ParchmentCard
                    className={`text-center p-3 relative ring-2 ring-offset-2 ring-offset-ink-page ${RARITY_RING_COLORS[entry.item.rarity] || 'ring-transparent'}`}
                  >
                    <div className="flex items-center justify-center h-12 mb-1">
                      <RpgSprite
                        spriteKey={entry.item.sprite_key}
                        icon={entry.item.icon}
                        size={48}
                        alt={entry.item.name}
                      />
                    </div>
                    <div className="font-body text-xs font-medium truncate">
                      {entry.item.name}
                    </div>
                    <div className="flex items-center justify-center mt-1.5">
                      <span
                        className={`text-micro px-1.5 py-0.5 rounded-full font-script uppercase tracking-wider ${
                          RARITY_PILL_COLORS[entry.item.rarity] || ''
                        }`}
                      >
                        {entry.item.rarity_display}
                      </span>
                    </div>
                    {(entry.available_actions || []).map((action) => (
                      <Button
                        key={action.id}
                        size="sm"
                        variant={action.to ? 'secondary' : 'primary'}
                        onClick={() => handleAction(entry, action)}
                        disabled={busyId === entry.id}
                        className="mt-2 w-full"
                      >
                        {busyId === entry.id ? 'Working…' : action.label}
                      </Button>
                    ))}
                    {entry.quantity > 1 && (
                      <div className="absolute -top-1.5 -right-1.5 min-w-[22px] h-[22px] px-1 rounded-full bg-ember-deep text-ink-page-rune-glow font-rune text-tiny font-bold flex items-center justify-center border border-ember">
                        ×{entry.quantity}
                      </div>
                    )}
                  </ParchmentCard>
                </motion.div>
              ))}
            </motion.div>
          </section>
        ))
      )}
    </div>
  );
}

function effectMessage(effect) {
  const messages = {
    streak_freeze: 'Your streak is protected for the next missed day.',
    xp_boost: 'Your next XP gains are boosted.',
    coin_boost: 'Your coin earnings are boosted.',
    drop_boost: 'Your drop chances are boosted.',
    growth_tonic: 'Your next pet feeds will grow more.',
    morale_tonic: 'Your next pet feeds will grow more.',
    rage_breaker: 'A boss rage shield was cleared.',
    growth_surge: 'Your active pet gained growth.',
    feast_platter: 'Your pets shared the feast.',
    mystery_box: 'A surprise item was added to your Satchel.',
    lucky_dip: 'A cosmetic prize was drawn.',
    quest_reroll: 'A new trial has started.',
    skill_tonic: 'One of your skills gained XP.',
    food_basket: 'Food was added to your Satchel.',
  };
  return messages[effect] || 'Its effect has been applied.';
}
