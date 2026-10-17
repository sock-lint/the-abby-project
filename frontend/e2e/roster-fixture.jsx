import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import roster from '../../shared/catalog/companion-roster.json';
import CompanionPreview from '../src/components/companion/CompanionPreview';
import FamilyStagePreview from '../src/components/companion/FamilyStagePreview';
import Button from '../src/components/Button';
import { SelectField } from '../src/components/form';
import { stagedRosterRelease } from '../src/companion/sharedRosterRelease';
import '../src/index.css';

const retained = { lineage_id: 'chick', species_slug: 'chick', sprite_key: 'cute-chick', name: 'Chick', egg: { item_slug: 'chick-egg' } };
const families = [...roster.families, retained];
const base = { id: 902, name: 'Base', slug: 'base', rarity: 'common' };
export default function Fixture() {
  const [lineage, setLineage] = useState(families[0].lineage_id), [stage, setStage] = useState('baby');
  const family = families.find(({ lineage_id }) => lineage_id === lineage);
  const [version, setVersion] = useState(0), [visible, setVisible] = useState(true);
  const species = { id: 901, slug: family.species_slug, sprite_key: family.sprite_key, name: family.name, icon: '🐾' };
  const pet = { id: 900, species, potion: base, lifecycle_stage: stage, growth_points: stage === 'baby' ? 0 : stage === 'middle' ? 50 : 100,
    evolved_to_mount: stage === 'grown', evolution_stage: lineage === 'chick' ? { baby: 'chick', middle: 'fledgling', grown: 'bird' }[stage] : null,
    happiness_level: 'happy', catalog_available: true, is_active: true, refresh_version: version };
  const egg = { id: 903, slug: family.egg.item_slug, name: `${family.name} Egg`, item_type: 'egg', pet_species_slug: family.species_slug,
    pet_species_name: family.name, metadata: { species: family.species_slug }, catalog_available: true };
  const installed = stagedRosterRelease();
  return <main className="max-w-3xl mx-auto p-4 space-y-4">
    <h1 className="text-lede font-bold">Private companion roster acceptance</h1>
    <p>Local synthetic ownership and preview. No accounts, production data or progression writes.</p>
    <SelectField label="Fixture family" value={lineage} onChange={(event) => { setLineage(event.target.value); setStage('baby'); setVisible(true); }}>
      {families.map((entry) => <option key={entry.lineage_id} value={entry.lineage_id}>{entry.lineage_id}</option>)}
    </SelectField>
    <div className="flex flex-wrap gap-2">
      {['egg', 'baby', 'middle', 'grown'].map((value) => <Button key={value} onClick={() => setStage(value)}>Set {value}</Button>)}
      <Button onClick={() => setVersion((value) => value + 1)}>Reload saved companion</Button>
      <Button onClick={() => setVisible((value) => !value)}>{visible ? 'Unmount presentation' : 'Mount presentation'}</Button>
    </div>
    <output aria-label="Fixture diagnostics" data-roster-installed={!!installed} data-selected-family={lineage} data-selected-stage={stage}
      data-roster-models={installed?.release.assets.filter((asset) => asset.kind === 'creature').length}>
      {lineage} · {stage} · {installed ? 'Exact private roster installed' : 'Private roster unavailable'}
    </output>
    {visible && (stage === 'egg' ? <FamilyStagePreview key={family.species_slug} item={egg} />
      : <CompanionPreview key={family.species_slug} variant="primary" creature={pet}><Button>Existing care control</Button></CompanionPreview>)}
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
