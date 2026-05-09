import { useId } from 'react';
import { Search, X } from 'lucide-react';
import { inputClass } from '../constants/styles';

/**
 * CatalogSearch — a small icon-prefixed text input used to filter long
 * catalog lists (Inventory, Badges, Skills, Rewards). The component is
 * controlled — pages own the value + filtered list memo. A clear button
 * appears once there is any value.
 */
export default function CatalogSearch({
  value,
  onChange,
  placeholder = 'Search…',
  ariaLabel = 'Filter catalog',
  className = '',
}) {
  const id = useId();
  return (
    <div className={`relative ${className}`}>
      <Search
        size={16}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-whisper pointer-events-none"
        aria-hidden="true"
      />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`${inputClass} pl-9 pr-9`}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Clear filter"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-whisper hover:text-ink-primary p-1 rounded"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
