import { motion } from 'framer-motion';
import { Crown, Map as MapIcon, Hourglass } from 'lucide-react';
import Button from '../../../components/Button';
import AddToCalendar from '../../../components/AddToCalendar';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { petSpriteKeys } from '../../../components/rpg/petSpriteKeys';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import { RARITY_HALO } from '../../../components/atlas/mastery.constants';
import { creatureLabel } from '../../../companion/appearance';
import { companionFormName } from '../../../companion/lifecycle';
import { daysUntilReady, formatExpeditionRemaining } from './party.constants';
import { companionRarity } from '../../../companion/rarity';

export default function OwnedMountGrid({ mounts, working, onActivate, onPreview, onClaim, onLaunch, label = 'Your grown pets' }) {
  return (
        <div role="list" aria-label={label} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {mounts.map((mount) => {
            const cooldownDaysLeft = daysUntilReady(mount.last_bred_at);
            const expedition = mount.active_expedition;
            const isOut = !!expedition && expedition.status === 'active';
            const isReady = isOut && expedition.is_ready;
            const remainingLabel = isOut
              ? formatExpeditionRemaining(expedition.seconds_remaining)
              : null;
            return (
              <motion.div key={mount.id} role="listitem" whileHover={{ y: -2 }}>
                <ParchmentCard
                  className={`text-center transition-all ${
                    mount.is_active
                      ? 'ring-2 ring-offset-2 ring-offset-ink-page ring-gold-leaf'
                      : ''
                  } ${isOut && !isReady ? 'opacity-80' : ''}`}
                >
                  <div className="flex items-center justify-center h-20 mb-1">
                    <div
                      className={`relative inline-flex items-center justify-center rounded-full p-1.5 bg-ink-page-aged/40 ${
                        RARITY_HALO[companionRarity(mount)] || RARITY_HALO.common
                      }`}
                    >
                      <RpgSprite
                        {...petSpriteKeys(mount, 'mount')}
                        icon={mount.species.icon}
                        size={64}
                        className="rounded-full"
                        alt={creatureLabel(mount, 'mount')}
                        potionSlug={mount.potion.slug}
                        dim={isOut && !isReady ? 'stale' : null}
                      />
                    </div>
                  </div>
                  <div className="font-body text-body font-medium leading-tight break-words">
                    {creatureLabel(mount, 'mount')}
                  </div>
                  <div
                    className={`font-script text-tiny uppercase tracking-wider ${
                      RARITY_TEXT_COLORS[companionRarity(mount)]
                    }`}
                  >
                    {companionRarity(mount)}
                  </div>
                  <div className="font-script text-tiny text-gold-leaf mt-1">grown pet</div>
                  {onPreview && <Button size="sm" variant="ghost" className="mt-1 w-full" onClick={() => onPreview(mount.id)} aria-label={`Visit ${creatureLabel(mount, 'mount')}`}>Spend time together</Button>}
                  {isOut && !isReady && (
                    <div className="mt-1 space-y-1">
                      <div className="font-script text-tiny text-sheikah-teal-deep flex items-center justify-center gap-1">
                        <Hourglass size={10} aria-hidden="true" /> exploring · {remainingLabel}
                      </div>
                      <AddToCalendar
                        event={{
                          id: `expedition:${expedition.id}`,
                          title: `Expedition return: ${creatureLabel(mount, 'mount')}`,
                          start: expedition.returns_at,
                          description: 'Check on your returning pet in The Abby Project.',
                          path: '/bestiary?tab=mounts',
                        }}
                      />
                    </div>
                  )}
                  {!isOut && mount.can_breed !== false && cooldownDaysLeft !== null && (
                    <div className="mt-1 font-script text-tiny text-ink-whisper">
                      resting · {cooldownDaysLeft}d
                    </div>
                  )}
                  {!isOut && mount.can_breed !== false && cooldownDaysLeft === null && (
                    <div className="mt-1 font-script text-tiny text-moss">
                      ready to breed
                    </div>
                  )}
                  {mount.is_active ? (
                    <div className="mt-1 font-script text-tiny text-gold-leaf flex items-center justify-center gap-1">
                      <Crown size={10} /> active
                    </div>
                  ) : (
                    // <Button> for the 44px floor these tile actions were
                    // missing (~30px before). The gold/teal tints stay as
                    // overrides — colour is the Bestiary's own vocabulary for
                    // "mount action" vs "expedition action".
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onActivate(mount.id)}
                      disabled={working || isOut}
                      className="mt-2 w-full !bg-gold-leaf/20 !text-ember-deep !border-gold-leaf/60 hover:!bg-gold-leaf/30 disabled:cursor-not-allowed"
                    >
                      {working ? 'Setting…' : 'Set active'}
                    </Button>
                  )}
                  {isReady ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onClaim(expedition.id)}
                      disabled={working}
                      className="mt-1 w-full !bg-gold-leaf/30 !text-ember-deep !border-gold-leaf/80 hover:!bg-gold-leaf/40 disabled:cursor-not-allowed animate-gilded-glint"
                      aria-label={`Claim expedition rewards for ${companionFormName(mount.species, mount.potion, 'grown')}`}
                    >
                      {working ? 'Claiming…' : 'Claim rewards'}
                    </Button>
                  ) : !isOut && mount.expedition_available === false ? (
                    <p className="mt-2 text-caption text-ink-secondary">Explored today · another trip tomorrow</p>
                  ) : !isOut ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onLaunch(mount)}
                      disabled={working}
                      className="mt-1 w-full inline-flex items-center justify-center gap-1 !bg-sheikah-teal-deep/15 !text-sheikah-teal-deep !border-sheikah-teal-deep/50 hover:!bg-sheikah-teal-deep/25 disabled:cursor-not-allowed"
                      aria-label={`Send ${companionFormName(mount.species, mount.potion, 'grown')} on an expedition`}
                    >
                      <MapIcon size={11} aria-hidden="true" /> Expedition
                    </Button>
                  ) : null}
                </ParchmentCard>
              </motion.div>
            );
          })}
        </div>
  );
}
