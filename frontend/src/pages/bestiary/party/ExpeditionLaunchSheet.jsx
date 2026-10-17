import { useState } from 'react';
import { Map as MapIcon, Hourglass, Backpack } from 'lucide-react';
import { CoinIcon } from '../../../components/icons/JournalIcons';
import BottomSheet from '../../../components/BottomSheet';
import Button from '../../../components/Button';
import ErrorAlert from '../../../components/ErrorAlert';
import { startExpedition } from '../../../api';
import usePetMutationGuard from './usePetMutationGuard';
import { companionFormName } from '../../../companion/lifecycle';

// Tier metadata mirrors apps/pets/expeditions.py::TIER_CONFIG so the UI
// reads truthful copy without an extra round-trip. If the backend table
// changes, update both — there's no need to API-fetch a list this short.
const TIERS = [
  {
    key: 'short',
    label: 'Short expedition',
    duration_label: '2 hours',
    coins_label: '~15 coins',
    items_label: '1 item',
    flavor: 'A short trip with mostly common finds.',
  },
  {
    key: 'standard',
    label: 'Standard expedition',
    duration_label: '4 hours',
    coins_label: '~35 coins',
    items_label: '2 items',
    flavor: 'A longer trip with two items to collect.',
  },
  {
    key: 'long',
    label: 'Long expedition',
    duration_label: '8 hours',
    coins_label: '~75 coins',
    items_label: '3 items',
    flavor: 'The longest trip, with better chances of rare finds.',
  },
];

/**
 * ExpeditionLaunchSheet — bottom sheet for sending a mount on an offline run.
 *
 * Once a mount is sent, it can't be sent again until the next local day
 * (matches apps/pets/expeditions.py::ExpeditionService.start). The mount
 * card on Mounts.jsx flips into the out-on-expedition state on success.
 */
export default function ExpeditionLaunchSheet({ mount, onDismiss, onLaunched }) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const beginMutation = usePetMutationGuard();

  if (!mount) return null;

  const handleLaunch = async (tier) => {
    const request = beginMutation();
    if (!request) return;
    setError('');
    setWorking(true);
    try {
      const expedition = await startExpedition(mount.id, tier);
      if (!request.isCurrent()) return;
      onLaunched?.(expedition);
      onDismiss?.();
    } catch (e) {
      if (request.isCurrent()) setError(e.message || 'Could not start expedition.');
    } finally {
      if (request.isCurrent()) setWorking(false);
      request.finish();
    }
  };

  return (
    <BottomSheet
      title={`Send ${companionFormName(mount.species, mount.potion, 'grown')} on an expedition`}
      onClose={onDismiss}
      disabled={working}
    >
      <div className="space-y-4">
        <p className="font-script text-body text-ink-whisper flex items-start gap-2">
          <MapIcon size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            Choose a duration. Your rewards are saved when the expedition
            starts, so you can collect them any time after it ends. Each grown pet
            can start one expedition per day.
          </span>
        </p>
        <ErrorAlert message={error} />
        <div className="space-y-2">
          {TIERS.map((tier) => (
            <button
              key={tier.key}
              type="button"
              onClick={() => handleLaunch(tier.key)}
              disabled={working}
              className="w-full text-left p-3 rounded-lg border border-ink-page-shadow bg-ink-page-aged hover:bg-ink-page-glow disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-sheikah-teal-deep"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-display italic text-lg text-ink-primary">
                  {tier.label}
                </div>
                <div className="font-script text-caption text-sheikah-teal-deep flex items-center gap-1">
                  <Hourglass size={11} aria-hidden="true" /> {tier.duration_label}
                </div>
              </div>
              <div className="font-body text-tiny text-ink-secondary mt-1">
                {tier.flavor}
              </div>
              <div className="flex items-center gap-3 mt-2 font-script text-tiny text-ink-whisper">
                <span className="inline-flex items-center gap-1">
                  <CoinIcon size={11} className="text-gold-leaf" aria-hidden="true" />
                  {tier.coins_label}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Backpack size={11} aria-hidden="true" />
                  {tier.items_label}
                </span>
              </div>
            </button>
          ))}
        </div>
        <div className="pt-2 border-t border-ink-page-shadow">
          <Button variant="ghost" onClick={onDismiss} disabled={working}>
            Cancel
          </Button>
        </div>
      </div>
    </BottomSheet>
  );
}
