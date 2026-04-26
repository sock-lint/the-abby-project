import { Lock } from 'lucide-react';
import BottomSheet from '../../../components/BottomSheet';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RuneBadge from '../../../components/journal/RuneBadge';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import { mountLabel, mountSpriteKey } from './bestiary.constants';

/**
 * BottomSheet detail view for a single species. Shows lore, food
 * preference, and the per-potion mount evolution row. Each potion tile
 * is illuminated when the user owns that mount, debossed otherwise.
 */
export default function SpeciesDetailSheet({ species, onClose }) {
  if (!species) return null;
  const ownedPotionIds = new Set(species.owned_mount_potion_ids || []);
  const eligible = species.available_potions || [];
  const discovered = !!species.discovered;

  return (
    <BottomSheet title={species.name} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-20 w-20 shrink-0 bg-ink-page-aged rounded-xl border border-ink-page-shadow">
            {discovered ? (
              <RpgSprite
                spriteKey={species.sprite_key}
                icon={species.icon}
                size={72}
                alt={species.name}
              />
            ) : (
              <span aria-hidden="true" style={{ filter: 'brightness(0)' }} className="text-5xl">
                {species.icon || '❓'}
              </span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            {species.food_preference && (
              <RuneBadge tone="teal" size="sm">
                prefers {species.food_preference}
              </RuneBadge>
            )}
            <div className="font-script text-tiny text-ink-whisper mt-2">
              {discovered
                ? `${ownedPotionIds.size} of ${eligible.length} mount variants collected`
                : 'undiscovered — hatch one to reveal'}
            </div>
          </div>
        </div>

        {species.description && (
          <ParchmentCard tone="bright">
            <div className="font-body text-body text-ink-primary leading-relaxed">
              {species.description}
            </div>
          </ParchmentCard>
        )}

        <section aria-labelledby="evolution-heading">
          <h3 id="evolution-heading" className="font-display text-base text-ink-primary mb-2">
            Evolution variants
          </h3>
          {eligible.length === 0 ? (
            <div className="font-script text-sm text-ink-whisper">
              no eligible potions for this species yet
            </div>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
              {eligible.map((potion) => {
                const owned = ownedPotionIds.has(potion.id);
                return (
                  <div
                    key={potion.id}
                    className={`text-center rounded-xl p-2 border transition-all ${
                      owned
                        ? 'bg-ink-page-aged border-gold-leaf/60 ring-1 ring-gold-leaf/40'
                        : 'bg-ink-page-shadow/30 border-ink-page-shadow opacity-70'
                    }`}
                    role="img"
                    aria-label={`${mountLabel(species.name, potion.name)} — ${
                      owned ? 'owned' : 'not yet evolved'
                    }`}
                  >
                    <div className="flex items-center justify-center h-12">
                      <span style={owned ? undefined : { filter: 'brightness(0.4) saturate(0)' }}>
                        <RpgSprite
                          spriteKey={mountSpriteKey(species.sprite_key)}
                          fallbackSpriteKey={species.sprite_key}
                          icon={species.icon}
                          size={48}
                          alt=""
                          potionSlug={potion.slug}
                        />
                      </span>
                    </div>
                    <div className="font-body text-tiny text-ink-primary truncate mt-1">
                      {potion.name}
                    </div>
                    <div
                      className={`font-script text-micro uppercase tracking-wider ${
                        RARITY_TEXT_COLORS[potion.rarity] || ''
                      }`}
                    >
                      {potion.rarity}
                    </div>
                    {!owned && (
                      <div className="mt-1 inline-flex items-center gap-0.5 font-script text-micro text-ink-whisper">
                        <Lock size={9} aria-hidden="true" />
                        locked
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section aria-labelledby="hatch-hints-heading">
          <h3 id="hatch-hints-heading" className="font-display text-base text-ink-primary mb-1">
            How to hatch
          </h3>
          <p className="font-script text-sm text-ink-whisper">
            pair a {species.name} egg with{' '}
            {eligible.length === 0
              ? 'any potion'
              : eligible.length === 1
                ? `the ${eligible[0].name} potion`
                : `one of: ${eligible.map((p) => p.name).join(', ')}`}{' '}
            in the Hatchery
          </p>
        </section>
      </div>
    </BottomSheet>
  );
}
