import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CompanionPreview from '../src/components/companion/CompanionPreview';
import FamilyStagePreview from '../src/components/companion/FamilyStagePreview';
import RpgSprite from '../src/components/rpg/RpgSprite';
import CatalogIcon from '../src/components/rpg/CatalogIcon';
import { petSpriteKeys } from '../src/components/rpg/petSpriteKeys';
import { resolveAppearance } from '../src/companion/appearance';
import { stagedElementalRelease } from '../src/companion/sharedElementalRelease';
import { companionFormName } from '../src/companion/lifecycle';
import Button from '../src/components/Button';
import { SelectField } from '../src/components/form';
import '../src/index.css';

const families = [
  { slug: 'chick', sprite_key: 'cute-chick', name: 'Chick', egg: 'chick-egg' },
  { slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf', name: 'Wolf', egg: 'meshtint-wolf-egg' },
];
const stages = ['baby', 'middle', 'grown'];
const potionFor = (slug) => ({ id: slug === 'fire' ? 902 : 903, slug, name: slug === 'fire' ? 'Fire' : 'Ice', rarity: 'rare' });
const storageKey = 'abby_synthetic_elemental_fixture';
const uiImages = ['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail'];
function loadFixture() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (families.some(({ slug }) => slug === saved?.species) && ['fire', 'ice'].includes(saved.potion) && stages.includes(saved.stage)) return saved;
  } catch { /* This local test fixture contains no account data. */ }
  return { species: 'chick', potion: 'fire', stage: 'baby' };
}
function creature(family, potion, stage) {
  return { id: 900, species: { id: 901, ...family, icon: '🐾' }, potion: potionFor(potion), lifecycle_stage: stage,
    growth_points: stage === 'baby' ? 49 : stage === 'middle' ? 50 : 100, evolved_to_mount: stage === 'grown',
    evolution_stage: null, happiness_level: 'happy', catalog_available: true, is_active: true };
}

function Portraits() {
  return <section className="space-y-3" aria-label="Elemental portrait and catalog images">
    <h2 className="text-lede font-bold">Exact stage portraits and catalog images</h2>
    <div className="grid grid-cols-2 gap-3">
      {families.flatMap((family) => ['fire', 'ice'].flatMap((potion) => stages.map((stage) => {
        const pet = creature(family, potion, stage), id = `${family.slug}-${potion}-${stage}`;
        const label = `${pet.potion.name} ${companionFormName(pet.species, pet.potion, stage)}`;
        return <figure key={id} data-testid={id} className="min-w-0 text-center">
          <RpgSprite {...petSpriteKeys(pet)} potionSlug={potion} size={128} alt={label} />
          <figcaption className="text-caption">{label}</figcaption>
        </figure>;
      })))}
      {uiImages.map((id) => <figure key={id} data-testid={id} className="min-w-0 text-center">
        <CatalogIcon assetId={id} icon="✨" size={64} alt={id} />
        <figcaption className="text-caption break-words">{id}</figcaption>
      </figure>)}
    </div>
  </section>;
}

export default function Fixture() {
  const [saved, setSaved] = useState(loadFixture), [mode, setMode] = useState('live');
  const [visible, setVisible] = useState(true), [unknown, setUnknown] = useState(false), [version, setVersion] = useState(0);
  const family = families.find(({ slug }) => slug === saved.species), potion = potionFor(saved.potion);
  const pet = { ...creature(family, saved.potion, saved.stage), refresh_version: version,
    ...(unknown ? { species: { slug: 'unsupported-elemental', sprite_key: 'unavailable-elemental', name: 'Saved companion', icon: '🐾' } } : {}) };
  const item = { id: 904, slug: family.egg, name: `${family.name} Egg`, item_type: 'egg',
    pet_species_slug: family.slug, pet_species_name: family.name, metadata: { species: family.slug }, catalog_available: true };
  const staged = stagedElementalRelease(), appearance = resolveAppearance(pet);
  useEffect(() => localStorage.setItem(storageKey, JSON.stringify(saved)), [saved]);
  return <main className="max-w-3xl mx-auto p-4 space-y-4">
    <h1 className="text-lede font-bold">Private elemental companion acceptance</h1>
    <p>Local synthetic ownership and previews. No account data or progression writes.</p>
    <SelectField label="Fixture species" value={saved.species} onChange={(event) => { setSaved({ ...saved, species: event.target.value, stage: 'baby' }); setUnknown(false); }}>
      {families.map(({ slug, name }) => <option key={slug} value={slug}>{name}</option>)}
    </SelectField>
    <SelectField label="Fixture potion" value={saved.potion} onChange={(event) => { setSaved({ ...saved, potion: event.target.value, stage: 'baby' }); setUnknown(false); }}>
      <option value="fire">Fire</option><option value="ice">Ice</option>
    </SelectField>
    <SelectField label="Fixture surface" value={mode} onChange={(event) => { setMode(event.target.value); setUnknown(false); }}>
      <option value="live">Owned companion</option><option value="hatchery">Hatchery preview</option><option value="portraits">Portraits and catalog</option>
    </SelectField>
    <div className="flex flex-wrap gap-2">
      {stages.map((stage) => <Button key={stage} onClick={() => { setSaved({ ...saved, stage }); setUnknown(false); }}>Set {stage}</Button>)}
      <Button onClick={() => setVersion((value) => value + 1)}>Reload saved companion</Button>
      <Button onClick={() => setUnknown(true)}>Use unsupported identity</Button>
      <Button onClick={() => setVisible((value) => !value)}>{visible ? 'Unmount presentation' : 'Mount presentation'}</Button>
    </div>
    <output aria-label="Fixture diagnostics" data-elemental-installed={!!staged} data-selected-species={saved.species}
      data-selected-potion={saved.potion} data-selected-stage={saved.stage} data-appearance-id={appearance?.assetId}
      data-populated-woodland={!!appearance?.woodland}>
      {saved.species} · {saved.potion} · {saved.stage} · {staged ? 'Exact private release installed' : 'Private release unavailable'}
      {' · '}{appearance?.woodland ? 'Populated Woodland installed' : 'Populated Woodland unavailable'}
    </output>
    {visible && (mode === 'portraits' ? <Portraits /> : mode === 'hatchery'
      ? <FamilyStagePreview key={`${family.slug}:${potion.slug}`} item={item} potion={potion} />
      : <CompanionPreview variant="primary" creature={pet}><Button>Existing care control</Button></CompanionPreview>)}
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
