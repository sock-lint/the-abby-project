import { motion } from 'framer-motion';
import { Crown, Star } from 'lucide-react';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { petSpriteKeys } from '../../../components/rpg/petSpriteKeys';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import { RARITY_HALO } from '../../../components/atlas/mastery.constants';
import { HAPPINESS_WHISPER } from './party.constants';
import { creatureLabel } from '../../../companion/appearance';

export default function OwnedPetGrid({ pets, selectedPetId, onSelect, label = 'Your companions' }) {
  return (
        <div role="list" aria-label={label} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {pets.map((pet) => (
            <motion.div key={pet.id} role="listitem" whileHover={{ y: -2 }}>
              <ParchmentCard
                className={`transition-all ${
                  pet.is_active
                    ? `ring-2 ring-offset-2 ring-offset-ink-page ring-moss`
                    : ''
                }`}
              >
                <button
                  type="button"
                  className="w-full rounded-lg text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep"
                  aria-label={`Care for ${creatureLabel(pet)}`}
                  aria-expanded={selectedPetId === pet.id}
                  onClick={() => onSelect(pet)}
                >
                  <div className="flex items-center justify-center h-16 mb-1">
                    <div
                      className={`relative inline-flex items-center justify-center rounded-full p-1 bg-ink-page-aged/40 ${
                        RARITY_HALO[pet.potion.rarity] || RARITY_HALO.common
                      }`}
                    >
                      <RpgSprite
                        {...petSpriteKeys(pet)}
                        icon={pet.species.icon}
                        size={56}
                        className="rounded-full"
                        alt={creatureLabel(pet)}
                        potionSlug={pet.potion.slug}
                        dim={
                          pet.evolved_to_mount
                            ? null
                            : pet.happiness_level && pet.happiness_level !== 'happy'
                              ? pet.happiness_level
                              : null
                        }
                      />
                    </div>
                  </div>
                  <div className="font-body text-body font-medium leading-tight break-words">
                    {creatureLabel(pet)}
                  </div>
                  <div
                    className={`font-script text-tiny uppercase tracking-wider ${
                      RARITY_TEXT_COLORS[pet.potion.rarity]
                    }`}
                  >
                    {pet.potion.rarity}
                  </div>
                  {!pet.evolved_to_mount && HAPPINESS_WHISPER[pet.happiness_level] && (
                    <div className="font-script text-tiny text-ink-whisper italic mt-0.5">
                      {HAPPINESS_WHISPER[pet.happiness_level]}
                    </div>
                  )}
                  {!pet.evolved_to_mount && (
                    <div className="mt-2">
                      <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-sheikah-teal-deep via-sheikah-teal to-gold-leaf"
                          style={{ width: `${pet.growth_points}%` }}
                        />
                      </div>
                      <div className="font-rune text-micro text-ink-whisper mt-0.5">
                        {pet.growth_points}/100
                      </div>
                    </div>
                  )}
                  {pet.evolved_to_mount && (
                    <div className="mt-1 font-script text-tiny text-gold-leaf flex items-center justify-center gap-1">
                      <Crown size={10} /> evolved
                    </div>
                  )}
                  {pet.is_active && (
                    <div className="mt-1 font-script text-tiny text-moss flex items-center justify-center gap-1">
                      <Star size={10} /> active
                    </div>
                  )}
                </button>

              </ParchmentCard>
            </motion.div>
          ))}
        </div>
  );
}
