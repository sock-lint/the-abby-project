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
        className={`${inputClass} pl-9 pr-11`}
      />
      {/* Clear button owns a full-height 44px column at the right edge (the
          input reserves pr-11 for it). A ~22px icon-sized target meant a
          missed tap landed in the field and popped the keyboard open —
          the exact opposite of what "clear the filter" is asking for. */}
      {localValue && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear filter"
          className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-ink-whisper hover:text-ink-primary rounded-r-lg"
        >
          <X size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
