import { isTaxonomyAvailable, taxonomyChoices, taxonomyOptionLabel } from '../../utils/taxonomy';

export default function TaxonomyOptions({ entries, selected, kind }) {
  const retainedMissing = selected != null && selected !== '' && !entries.some((entry) => String(entry.id) === String(selected));
  return <>
    {retainedMissing && <option value={selected} disabled>Retained {kind} (#{selected}) · not listed</option>}
    {taxonomyChoices(entries, selected).map((entry) => (
    <option key={entry.id} value={entry.id} disabled={!isTaxonomyAvailable(entry)}>
      {entry.icon ? `${entry.icon} ` : ''}{taxonomyOptionLabel(entry, entry.name, kind)}
    </option>
    ))}
  </>;
}
