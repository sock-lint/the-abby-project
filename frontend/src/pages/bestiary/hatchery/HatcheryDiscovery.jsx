import { useId } from 'react';
import { Link } from 'react-router-dom';
import Button from '../../../components/Button';
import { SelectField } from '../../../components/form';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import ProgressBar from '../../../components/ProgressBar';
import FamilyStagePreview from '../../../components/companion/FamilyStagePreview';
import { rosterFamily } from '../../../companion/sharedRosterRelease';
import { isCatalogAvailable } from '../../../utils/catalogAvailability';

// This is presentation metadata, never an inventory entry or a hatch request.
// A server-approved family must also match the exact registered artwork identity.
function previewEgg(species) {
  const chick = species.slug === 'chick' && species.sprite_key === 'cute-chick';
  const family = rosterFamily(species, { slug: 'base' });
  if (!chick && !family) return null;
  return {
    id: 'preview:' + species.slug,
    slug: chick ? 'chick-egg' : family.egg.item_slug,
    name: species.name + ' Egg',
    item_type: 'egg',
    pet_species_slug: species.slug,
    pet_species_name: species.name,
    metadata: { species: species.slug },
  };
}

function appearanceStatus(species, potion, stable, incubation, collectionUnavailable, incubationUnavailable) {
  const owned = [...(stable?.pets || []), ...(stable?.mounts || [])].some((pet) =>
    pet.species?.slug === species.slug && pet.potion?.slug === potion.slug);
  if (stable && !collectionUnavailable && owned) return 'Owned';
  const incubatingSpecies = incubation?.species?.slug || incubation?.egg?.pet_species_slug;
  const incubatingPotion = incubation?.potion_type?.slug || incubation?.potion?.metadata?.variant;
  if (!incubationUnavailable && incubation && incubation.status !== 'hatched'
    && incubatingSpecies === species.slug && incubatingPotion === potion.slug) {
    return incubation.is_ready ? 'Ready to hatch' : 'Incubating';
  }
  return !stable || collectionUnavailable || incubationUnavailable ? 'Collection status unavailable' : 'Not collected';
}

function ChallengeProgress({ challenge, potion, species }) {
  const attempt = challenge.attempt;
  const progress = Number(attempt?.progress);
  const target = Number(attempt?.target);
  const offerTarget = Number(challenge.target);
  const measured = attempt && Number.isFinite(progress) && Number.isFinite(target) && target > 0;
  const status = {
    active: 'In progress', completed: 'Completed', expired: 'Attempt ended',
    failed: 'Attempt ended', paused: 'Paused', scheduled: 'Upcoming', upcoming: 'Upcoming',
  }[attempt?.status] || 'Saved attempt';
  return <li className="rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 space-y-2">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h4 className="font-semibold text-body text-ink-primary">{attempt?.name || challenge.name}</h4>
      <span className="text-caption text-ink-secondary">{attempt ? status : challenge.offer_available ? 'Guaranteed reward' : 'Offer unavailable'}</span>
    </div>
    <p className="text-caption text-ink-secondary">
      {challenge.offer_available
        ? species.name + ' egg + ' + potion.name + ' potion'
        : attempt ? 'Saved challenge promise. This offer is unavailable for new attempts.'
          : 'This challenge is not currently available for new attempts. Open Challenges for details.'}
    </p>
    {measured && <>
      <p className="text-body text-ink-primary">{progress} of {target}</p>
      <ProgressBar value={progress} max={target} aria-label={(attempt.name || challenge.name) + ' progress'} />
    </>}
    {!attempt && <p className="text-caption text-ink-secondary">
      {Number.isFinite(offerTarget) && offerTarget > 0 ? 'Challenge target: ' + offerTarget + '. ' : ''}
      {challenge.offer_available ? 'No saved attempt yet; matching activities count automatically.' : 'Check the current requirements in Challenges.'}
    </p>}
    {attempt?.retry_available && <p className="text-caption text-ink-secondary">You can try again from Challenges.</p>}
    <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep"
      to={challenge.path || '/quests?tab=trials'}>View {(attempt?.name || challenge.name)}</Link>
  </li>;
}

export default function HatcheryDiscovery({
  catalog, stable, incubation, loading, refreshing, catalogError,
  stableError, incubationError, selection = {}, onSelect,
}) {
  const headingId = useId();
  const families = (catalog?.species || []).filter((species) => isCatalogAvailable(species)
    && species.available_potions?.some(isCatalogAvailable));
  const species = families.find((entry) => entry.slug === selection.speciesSlug) || families[0];
  const potions = (species?.available_potions || []).filter(isCatalogAvailable);
  const potion = potions.find((entry) => entry.slug === selection.potionSlug)
    || potions.find((entry) => entry.slug === 'base') || potions[0];
  const item = species && previewEgg(species);
  const challenges = potion?.acquisition_challenges || [];
  const collected = potions.filter((entry) =>
    appearanceStatus(species, entry, stable, incubation, stableError, incubationError) === 'Owned').length;

  return <ParchmentCard>
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} className="font-display font-bold text-lede text-ink-primary">Explore companions</h2>
      <p className="text-body text-ink-secondary">
        Preview appearances and growth stages before you find an egg. Browsing does not use your supplies.
      </p>
      {!catalog && loading && <p role="status" className="text-body text-ink-secondary">Loading companion appearances…</p>}
      {catalogError && <p role="status" className="text-body text-ink-secondary">
        {catalog ? 'Showing the last loaded appearances. Use Try again above to refresh the catalog.'
          : 'Companion appearances are unavailable. Use Try again above to reload the catalog.'}
      </p>}
      {refreshing && <p role="status" className="text-caption text-ink-secondary">Refreshing appearances and challenge progress…</p>}
      {catalog && !families.length && <p className="text-body text-ink-secondary">No companion appearances are available to browse right now.</p>}
      {species && potion && <>
        <SelectField label="Explore a family" value={species.slug}
          onChange={(event) => onSelect({ speciesSlug: event.target.value, potionSlug: potion.slug })}>
          {families.map((family) => <option key={family.slug} value={family.slug}>{family.name || family.slug}</option>)}
        </SelectField>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold text-body text-ink-primary">{species.name} appearances</h3>
          <p className="text-caption text-ink-secondary">{stable && !stableError
            ? collected + ' of ' + potions.length + ' appearances collected'
            : 'Collection status unavailable'}</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" role="group" aria-label="Preview appearance">
          {potions.map((entry) => <Button key={entry.slug} variant={entry.slug === potion.slug ? 'secondary' : 'ghost'}
            className="min-w-0 text-left" aria-label={entry.name + ' appearance'} aria-pressed={entry.slug === potion.slug}
            onClick={() => onSelect({ speciesSlug: species.slug, potionSlug: entry.slug })}>
            <span className="block font-semibold">{entry.name}</span>
            <span className="block text-caption">{appearanceStatus(species, entry, stable, incubation, stableError, incubationError)}</span>
          </Button>)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
          {item ? <FamilyStagePreview key={species.slug} item={item} potion={potion} initialStage="baby" />
            : <p className="text-body text-ink-secondary">Artwork preview is unavailable for this family.</p>}
          <div className="space-y-3">
            <p role="status" aria-label="Appearance collection status" className="text-body font-semibold text-ink-primary">
              {appearanceStatus(species, potion, stable, incubation, stableError, incubationError)}
            </p>
            <h3 className="font-semibold text-body text-ink-primary">Earn this appearance</h3>
            <p className="text-body text-ink-secondary">
              Hatching uses one natural {species.name} egg and one {potion.name} potion. The chosen appearance stays with your companion as it grows.
            </p>
            {challenges.length ? <ul className="space-y-3" aria-label={potion.name + ' ' + species.name + ' challenges'}>
              {challenges.map((challenge) => <ChallengeProgress key={challenge.definition_id + ':' + (challenge.attempt?.id || 'offer')}
                challenge={challenge} potion={potion} species={species} />)}
            </ul> : <p className="text-body text-ink-secondary">Visit Challenges to find current egg and potion rewards.</p>}
            {!challenges.length && <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep"
              to="/quests?tab=trials">View challenge rewards</Link>}
          </div>
        </div>
      </>}
    </section>
  </ParchmentCard>;
}
