import { SelectField } from '../form';

// Shared parent context. The hook owns roster verification and URL state;
// this component stays presentational for gallery and other family views.
export default function ChildContext({ children: childOptions, selectedChildId, onSelect, actions }) {
  if (!childOptions?.length) return null;
  return <div className="flex flex-wrap items-end justify-between gap-3">
    <SelectField label="Viewing" value={selectedChildId ?? ''}
      onChange={(event) => onSelect(event.target.value)} className="min-w-0 w-full sm:max-w-xs sm:flex-1">
      {childOptions.map((child) => <option key={child.id} value={child.id}>
        {child.display_name || child.first_name || child.username}
      </option>)}
    </SelectField>
    {actions}
  </div>;
}
