import { forwardRef, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

/**
 * Select-only combobox with a themed listbox. Keep a native select for browser
 * validation, form data, forwarded refs and genuine React change events.
 * The listbox uses the browser's top layer while remaining inside its dialog.
 */
const Dropdown = forwardRef(function Dropdown({
  id, children, className = '', value, defaultValue, disabled, required,
  autoFocus, name, form, onChange, onInvalid, onFocus, onBlur,
  'aria-label': ariaLabel, 'aria-labelledby': ariaLabelledBy,
  'aria-describedby': describedBy, 'aria-invalid': invalid, 'aria-disabled': ariaDisabled,
  ...rest
}, forwardedRef) {
  const generatedId = useId();
  const controlId = id || generatedId;
  const listboxId = `${controlId}-listbox`;
  const triggerRef = useRef(null);
  const nativeRef = useRef(null);
  const listRef = useRef(null);
  const searchRef = useRef({ text: '', time: 0 });
  const revealSelectionRef = useRef(false);
  const [uncontrolledValue, setSelectedValue] = useState(String(defaultValue ?? ''));
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [position, setPosition] = useState(null);
  const [validationMessage, setValidationMessage] = useState('');
  const [options, setOptions] = useState([]);
  const selectedValue = value === undefined ? uncontrolledValue
    : options.find((option) => option.value === String(value))?.value ?? options.find((option) => !option.disabled)?.value ?? '';
  const selected = options.find((option) => option.value === selectedValue);
  const canUsePopover = typeof HTMLElement !== 'undefined' && 'showPopover' in HTMLElement.prototype;
  // aria-disabled keeps an unavailable control reachable with its help text.
  const unavailable = Boolean(disabled) || ariaDisabled === true || ariaDisabled === 'true';
  const isOpen = open && !unavailable;
  const visibleOptions = options.map((option, index) => ({ ...option, index })).filter((option) => !option.hidden);
  const enabledOptions = visibleOptions.filter((option) => !option.disabled);
  const currentActiveIndex = enabledOptions.some((option) => option.index === activeIndex)
    ? activeIndex : enabledOptions[0]?.index ?? -1;
  const optionGroups = [];
  for (const option of visibleOptions) {
    if (!optionGroups.length || optionGroups.at(-1).label !== option.group) {
      optionGroups.push({ label: option.group, options: [] });
    }
    optionGroups.at(-1).options.push(option);
  }

  // The rendered native options are the source of truth, including options
  // produced by child components, fragments, or changing optgroups.
  useLayoutEffect(() => {
    const select = nativeRef.current;
    if (!select) return undefined;
    const synchronize = () => {
      const next = Array.from(select.options).map((option) => {
        const group = option.parentElement?.tagName === 'OPTGROUP' ? option.parentElement : null;
        return {
          value: option.value,
          label: option.label,
          disabled: option.disabled || Boolean(group?.disabled),
          hidden: option.hidden || Boolean(group?.hidden),
          group: group?.label || null,
        };
      });
      setOptions((current) => JSON.stringify(current) === JSON.stringify(next) ? current : next);
      setSelectedValue(select.value);
      if (select.disabled) setOpen(false);
      if (select.validity.valid) setValidationMessage('');
    };
    synchronize();
    const observer = new MutationObserver(synchronize);
    observer.observe(select, { subtree: true, childList: true, attributes: true, characterData: true });
    return () => observer.disconnect();
  }, [value, defaultValue, children, unavailable]);

  useLayoutEffect(() => {
    if (revealSelectionRef.current) {
      revealSelectionRef.current = false;
      const trigger = triggerRef.current;
      const field = trigger?.closest('[data-dropdown-field]') || trigger;
      field?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
  }, [selectedValue, isOpen]);

  useLayoutEffect(() => {
    const select = nativeRef.current;
    const ownerForm = select?.form;
    if (!ownerForm) return undefined;
    const reset = (event) => {
      queueMicrotask(() => {
        if (!event.defaultPrevented && nativeRef.current) {
          setSelectedValue(nativeRef.current.value);
          setOpen(false);
          setValidationMessage('');
        }
      });
    };
    ownerForm.addEventListener('reset', reset);
    return () => ownerForm.removeEventListener('reset', reset);
  }, [form]);

  useLayoutEffect(() => {
    if (!isOpen) return undefined;
    const popup = listRef.current;
    const updatePosition = () => {
      const bounds = triggerRef.current.getBoundingClientRect();
      const viewport = window.visualViewport;
      const leftEdge = viewport?.offsetLeft || 0;
      const topEdge = viewport?.offsetTop || 0;
      const viewportWidth = viewport?.width || window.innerWidth;
      const viewportHeight = viewport?.height || window.innerHeight;
      const edge = 8;
      const gap = 6;
      const width = Math.min(Math.max(bounds.width, 200), viewportWidth - edge * 2);
      const below = topEdge + viewportHeight - bounds.bottom - gap - edge;
      const above = bounds.top - topEdge - gap - edge;
      const placeAbove = below < 176 && above > below;
      const maxHeight = Math.max(44, Math.min(320, placeAbove ? above : below));
      // Measure the visible top-layer menu at its final width. A closed
      // popover has no layout, and wrapped choices change its natural height.
      popup.style.width = `${width}px`;
      popup.style.maxHeight = `${maxHeight}px`;
      const height = popup.getBoundingClientRect().height;
      setPosition({
        left: Math.max(leftEdge + edge, Math.min(bounds.left, leftEdge + viewportWidth - width - edge)),
        top: Math.max(topEdge + edge, placeAbove ? bounds.top - gap - height : bounds.bottom + gap),
        width,
        maxHeight,
      });
    };
    if (canUsePopover) popup.showPopover();
    updatePosition();
    const dismiss = (event) => {
      if (!triggerRef.current?.contains(event.target) && !popup.contains(event.target)) {
        searchRef.current = { text: '', time: 0 };
        setOpen(false);
      }
    };
    const leave = (event) => {
      if (!triggerRef.current?.contains(event.target) && !popup.contains(event.target)) {
        searchRef.current = { text: '', time: 0 };
        setOpen(false);
      }
    };
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('focusin', leave);
    window.addEventListener('resize', updatePosition);
    document.addEventListener('scroll', updatePosition, true);
    window.visualViewport?.addEventListener('resize', updatePosition);
    window.visualViewport?.addEventListener('scroll', updatePosition);
    return () => {
      if (canUsePopover && popup.matches(':popover-open')) popup.hidePopover();
      document.removeEventListener('pointerdown', dismiss, true);
      document.removeEventListener('focusin', leave);
      window.removeEventListener('resize', updatePosition);
      document.removeEventListener('scroll', updatePosition, true);
      window.visualViewport?.removeEventListener('resize', updatePosition);
      window.visualViewport?.removeEventListener('scroll', updatePosition);
    };
  }, [isOpen, canUsePopover, options]);

  useLayoutEffect(() => {
    if (isOpen) document.getElementById(`${listboxId}-option-${currentActiveIndex}`)?.scrollIntoView?.({ block: 'nearest' });
  }, [currentActiveIndex, isOpen, listboxId]);

  function show(where = 'selected') {
    if (unavailable) return;
    searchRef.current = { text: '', time: 0 };
    const current = enabledOptions.find((option) => option.value === selectedValue);
    const initial = where === 'first' ? enabledOptions[0]
      : where === 'last' ? enabledOptions.at(-1)
        : current || enabledOptions[0];
    setActiveIndex(initial?.index ?? -1);
    setOpen(true);
  }

  function choose(index) {
    const option = options[index];
    if (!option || option.disabled || option.hidden || unavailable) return;
    const select = nativeRef.current;
    revealSelectionRef.current = true;
    if (select.value !== option.value) {
      select.value = option.value;
      select.dispatchEvent(new Event('input', { bubbles: true }));
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    searchRef.current = { text: '', time: 0 };
    setOpen(false);
    triggerRef.current?.focus({ preventScroll: true });
  }

  function typeahead(key, now) {
    const previous = now - searchRef.current.time < 700 ? searchRef.current.text : '';
    const text = previous + key.toLocaleLowerCase();
    searchRef.current = { text, time: now };
    const query = [...text].every((letter) => letter === text[0]) ? text[0] : text;
    const start = enabledOptions.findIndex((option) => option.index === activeIndex);
    const ordered = [...enabledOptions.slice(start + 1), ...enabledOptions.slice(0, start + 1)];
    const match = ordered.find((option) => option.label.trim().toLocaleLowerCase().startsWith(query));
    if (match) setActiveIndex(match.index);
    if (!isOpen) setOpen(true);
  }

  function handleKeyDown(event) {
    rest.onKeyDown?.(event);
    if (event.defaultPrevented || unavailable) return;
    if (event.key === 'Tab') { searchRef.current = { text: '', time: 0 }; setOpen(false); return; }
    if (event.key === 'Escape') {
      if (isOpen) { event.preventDefault(); event.stopPropagation(); setOpen(false); searchRef.current = { text: '', time: 0 }; }
      return;
    }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      searchRef.current = { text: '', time: 0 };
      if (!isOpen) { show(event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : 'selected'); return; }
      const current = enabledOptions.findIndex((option) => option.index === activeIndex);
      let next = current;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = enabledOptions.length - 1;
      else next = Math.max(0, Math.min(enabledOptions.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
      setActiveIndex(enabledOptions[next]?.index ?? -1);
      return;
    }
    // Space belongs to a phrase while typeahead is active. Otherwise it
    // retains the standard combobox open/confirm keyboard action.
    if (event.key === ' ' && searchRef.current.text && event.timeStamp - searchRef.current.time < 700
      && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      typeahead(event.key, event.timeStamp);
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (isOpen) choose(currentActiveIndex);
      else { searchRef.current = { text: '', time: 0 }; show(); }
      return;
    }
    if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      typeahead(event.key, event.timeStamp);
    }
  }

  const popup = isOpen && (
    <div
      ref={listRef}
      id={listboxId}
      role="listbox"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy || (!ariaLabel ? controlId : undefined)}
      popover={canUsePopover ? 'manual' : undefined}
      data-dropdown-listbox="true"
      className="fixed z-50 m-0 overflow-y-auto overscroll-contain rounded-xl border border-control-border bg-ink-page p-1.5 text-base text-ink-primary shadow-lg"
      style={{ ...position, visibility: position ? 'visible' : 'hidden', boxSizing: 'border-box' }}
      onPointerDown={(event) => {
        // Keep virtual focus for mouse presses. Touch/pen must retain their
        // default activation so the browser can synthesize the selection click.
        if (event.pointerType === 'mouse') event.preventDefault();
      }}
      // Compatibility mousedown from touch can focus the dialog ancestor.
      // Retain trigger focus until the following click commits the choice.
      onMouseDown={(event) => event.preventDefault()}
    >
      {visibleOptions.length === 0 && <div className="px-3 py-3 text-ink-secondary">No options available</div>}
      {optionGroups.map((group, index) => (
        <div key={index} role={group.label ? 'group' : undefined} aria-label={group.label || undefined}>
          {group.label && <div className="px-3 pb-1 pt-2 text-caption font-semibold text-ink-secondary" aria-hidden="true">{group.label}</div>}
          {group.options.map((option) => (
            <div
              key={option.index}
              id={`${listboxId}-option-${option.index}`}
              role="option"
              aria-selected={option.value === selectedValue}
              aria-disabled={option.disabled || undefined}
              data-value={option.value}
              data-active={option.index === currentActiveIndex ? 'true' : undefined}
              className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left whitespace-normal break-words ${option.disabled ? 'cursor-not-allowed opacity-50' : option.index === currentActiveIndex ? 'bg-sheikah-teal/15 text-ink-primary' : 'hover:bg-ink-page-aged'} ${option.value === selectedValue ? 'font-semibold' : ''}`}
              onPointerMove={() => { if (!option.disabled) setActiveIndex(option.index); }}
              onClick={() => choose(option.index)}
            >
              <span className="min-w-0 flex-1">{option.label}</span>
              <Check size={18} className={`shrink-0 text-sheikah-teal-deep ${option.value === selectedValue ? '' : 'invisible'}`} aria-hidden="true" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );

  return (
    <>
      <select
        {...rest}
        ref={(node) => {
          nativeRef.current = node;
          if (typeof forwardedRef === 'function') forwardedRef(node);
          else if (forwardedRef) forwardedRef.current = node;
        }}
        hidden
        aria-hidden="true"
        tabIndex={-1}
        value={value}
        defaultValue={defaultValue}
        disabled={unavailable}
        required={required}
        name={name}
        form={form}
        onChange={(event) => {
          setSelectedValue(event.currentTarget.value);
          if (event.currentTarget.validity.valid) setValidationMessage('');
          onChange?.(event);
        }}
        onInvalid={(event) => {
          onInvalid?.(event);
          event.preventDefault();
          setValidationMessage(event.currentTarget.validationMessage || 'Please choose an option.');
          triggerRef.current?.focus();
        }}
      >{children}</select>
      <button
        {...Object.fromEntries(Object.entries(rest).filter(([key]) => key.startsWith('aria-') || key.startsWith('data-') || key === 'title' || key === 'style'))}
        ref={triggerRef}
        id={controlId}
        type="button"
        role="combobox"
        data-dropdown-trigger="true"
        value={selectedValue}
        disabled={disabled}
        autoFocus={autoFocus}
        tabIndex={rest.tabIndex}
        form={form}
        title={rest.title || selected?.label}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        aria-describedby={[describedBy, !invalid && validationMessage ? `${controlId}-validation` : null].filter(Boolean).join(' ') || undefined}
        aria-invalid={invalid || (validationMessage ? 'true' : undefined)}
        aria-required={required || undefined}
        aria-disabled={unavailable || undefined}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-activedescendant={isOpen && currentActiveIndex >= 0 ? `${listboxId}-option-${currentActiveIndex}` : undefined}
        className={`${className} flex items-center justify-between gap-3 text-left disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50`}
        onClick={() => {
          // Safari does not focus buttons on pointer clicks. Virtual option
          // focus and modal Escape handling both belong to this trigger.
          triggerRef.current?.focus({ preventScroll: true });
          if (unavailable) return;
          searchRef.current = { text: '', time: 0 };
          if (isOpen) setOpen(false);
          else show();
        }}
        onKeyDown={handleKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      >
        <span className="min-w-0 flex-1 truncate">{selected?.label || '\u00a0'}</span>
        <ChevronDown size={18} className={`shrink-0 text-ink-secondary transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {!invalid && validationMessage && <p id={`${controlId}-validation`} role="alert" className="mt-1 text-caption text-ember-deep">{validationMessage}</p>}
      {popup && (canUsePopover ? popup : createPortal(popup, document.body))}
    </>
  );
});

export default Dropdown;
