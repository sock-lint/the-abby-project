import { useState } from 'react';
import bindings from '../../../../shared/catalog/artwork-bindings.json';
import ArtworkImage from '../../components/rpg/ArtworkImage';
import { SelectField } from '../../components/form';
import SectionHeader from '../../components/SectionHeader';

const rows = (group) => Object.values(group).map((row) => ({
  id: row.asset_id, name: row.name, scope: row.scope,
}));
const nestedRows = (group) => Object.entries(group).flatMap(([category, entries]) =>
  rows(entries).map((row) => ({ ...row, name: `${category} · ${row.name}` })));
const groups = {
  badges: { name: 'Badges', rows: rows(bindings.badges) },
  categories: { name: 'Categories', rows: rows(bindings.categories) },
  subjects: { name: 'Subjects', rows: nestedRows(bindings.subjects) },
  skills: { name: 'Skills', rows: nestedRows(bindings.skills) },
  items: { name: 'Items and accessories', rows: rows(bindings.items) },
  challenges: { name: 'Challenges', rows: rows(bindings.challenges) },
  birthday: { name: 'Birthday', rows: [{ id: bindings.birthday.asset_id, name: 'Birthday candle' }] },
};

/** Synthetic artwork inspection only; this view never changes a catalog record. */
export default function ArtworkShowcase() {
  const [group, setGroup] = useState('badges');
  const [size, setSize] = useState('40');
  const selected = groups[group];
  return <section id="design-artwork" aria-label="Catalog artwork" className="space-y-3 scroll-mt-4">
    <SectionHeader title="Catalog artwork" kicker="365 illustrations" />
    <p className="text-body text-ink-secondary">
      Read-only examples of the badge, skill, birthday and catalog artwork.
      Missing images keep their authored glyphs. Optional content and accessories retain their current availability.
    </p>
    <div className="grid sm:grid-cols-2 gap-3">
      <SelectField label="Artwork group" value={group} onChange={(event) => setGroup(event.target.value)}>
        {Object.entries(groups).map(([key, value]) => <option key={key} value={key}>{value.name} ({value.rows.length})</option>)}
      </SelectField>
      <SelectField label="Artwork size" value={size} onChange={(event) => setSize(event.target.value)}>
        {[24, 32, 40, 64, 96].map((value) => <option key={value} value={value}>{value} pixels</option>)}
      </SelectField>
    </div>
    <div role="group" aria-label={`${selected.name} artwork`} className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
      {selected.rows.map((row) => <figure key={row.id} data-artwork-example={row.id}
        className="min-w-0 flex flex-col items-center gap-2 rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-3">
        <span aria-hidden="true" className="inline-flex shrink-0 items-center justify-center" style={{ width: Number(size), height: Number(size) }}>
          <ArtworkImage assetId={row.id} size={Number(size)} fallback="✨" />
        </span>
        <figcaption className="text-caption text-ink-primary text-center break-words">{row.name}</figcaption>
      </figure>)}
    </div>
    <details className="rounded-lg border border-ink-page-shadow p-3 text-body text-ink-secondary">
      <summary className="cursor-pointer min-h-11 flex items-center">Integration and accessory limits</summary>
      <p>Application views use the server&apos;s read-only catalog_icon reference and retain readable names, rarity and locked states.</p>
      <p className="mt-2">The separate Crown fitting pilot is pinned for private evaluation. It covers native Chick, Fledgling and Bird takes. Egg, evolution transitions, other species and the other 16 accessories have no supported fit. Acquisition and equipping remain disabled.</p>
      <pre className="mt-2 whitespace-pre-wrap break-all text-caption">{'import ArtworkImage from "../components/rpg/ArtworkImage";\n<ArtworkImage assetId={record.catalog_icon} fallback={record.icon} />'}</pre>
    </details>
  </section>;
}
