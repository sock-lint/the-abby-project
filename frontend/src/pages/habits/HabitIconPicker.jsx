import { useId, useState } from 'react';
import { Check } from 'lucide-react';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { TextField } from '../../components/form';

const ICONS = [
  ['⚡', 'Lightning'],
  ['🪥', 'Toothbrush'],
  ['💧', 'Water'],
  ['📖', 'Book'],
  ['🛏️', 'Bed'],
  ['🏃', 'Running'],
  ['🧘', 'Meditation'],
  ['🍎', 'Apple'],
  ['🧹', 'Broom'],
  ['🎒', 'Backpack'],
  ['✏️', 'Pencil'],
  ['🎨', 'Art'],
  ['🎵', 'Music'],
  ['🤝', 'Helping hands'],
  ['📵', 'No phones'],
];

export default function HabitIconPicker({ value, onChange, disabled = false }) {
  const [expanded, setExpanded] = useState(false);
  const choicesId = useId();

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-2">
        <TextField
          label="Icon"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="⚡"
          disabled={disabled}
          className="min-w-0 flex-1"
        />
        <Button
          variant="secondary"
          size="sm"
          aria-label="Choose icon"
          aria-expanded={expanded}
          aria-controls={choicesId}
          disabled={disabled}
          onClick={() => setExpanded(!expanded)}
        >
          Choose
        </Button>
      </div>
      <div id={choicesId} hidden={!expanded}>
        <div role="group" aria-label="Suggested icons" className="grid grid-cols-5 gap-2">
          {ICONS.map(([icon, label]) => (
            <IconButton
              key={label}
              aria-label={label}
              aria-pressed={value === icon}
              title={label}
              variant="secondary"
              disabled={disabled}
              onClick={() => onChange(icon)}
              className={`relative text-lede ${value === icon ? 'ring-2 ring-royal' : ''}`}
            >
              <span aria-hidden="true">{icon}</span>
              {value === icon && <Check aria-hidden="true" size={12} className="absolute right-0 top-0 text-royal" />}
            </IconButton>
          ))}
        </div>
        <p className="mt-2 font-script text-caption text-ink-secondary">Choose an icon or type your own above.</p>
      </div>
    </div>
  );
}
