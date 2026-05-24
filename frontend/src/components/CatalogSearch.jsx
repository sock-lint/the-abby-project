import { useEffect, useId, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { inputClass } from '../constants/styles';

/**
 * CatalogSearch — a small icon-prefixed text input used to filter long
 * catalog lists (Inventory, Badges, Skills, Rewards). The component is
 * controlled — pages own the value + filtered list memo. A clear button
 * appears once there is any value.
 *
 * When `debounceMs` is provided, the input updates instantly for visual
 * feedback but the `onChange` callback is debounced by that many ms.
 */
export default function CatalogSearch({
  value,
  onChange,
  placeholder = 'Search…',
  ariaLabel = 'Filter catalog',
  debounceMs = 0,
  className = '',
}) {
  const id = useId();
  const [localValue, setLocalValue] = useState(value);
  const timerRef = useRef(null);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleChange = (next) => {
    setLocalValue(next);
    if (debounceMs > 0) {
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onChange(next), debounceMs);
    } else {
      onChange(next);
    }
  };

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const handleClear = () => {
    clearTimeout(timerRef.current);
    setLocalValue('');
    onChange('');
  };

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
        value={localValue}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`${inputClass} pl-9 pr-9`}
      />
      {localValue && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear filter"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-whisper hover:text-ink-primary p-1 rounded"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
