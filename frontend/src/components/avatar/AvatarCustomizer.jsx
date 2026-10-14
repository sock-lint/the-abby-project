import Button from '../Button';
import { SelectField } from '../form';

// Choices are resolved from the shared item registry and fit bindings before
// reaching these controls. A pack's source is not an equipment restriction.
export default function AvatarCustomizer({ avatarDefinition, configuration, onChange, disabled = false }) {
  return <div className="space-y-4">
    {avatarDefinition.presets.length > 0 && <fieldset disabled={disabled} className="space-y-2">
      <legend className="font-body font-bold text-lede text-ink-primary">Coordinated looks</legend>
      <div className="flex flex-wrap gap-2">
        {avatarDefinition.presets.map((preset) => <Button key={preset.id} variant="secondary" size="sm" disabled={disabled}
          aria-pressed={['appearance', 'accessories'].every((scope) => Object.entries(preset[scope]).every(([key, value]) => configuration[scope][key] === value))}
          onClick={() => onChange({ appearance: preset.appearance, accessories: preset.accessories })}>{preset.label}</Button>)}
      </div>
    </fieldset>}
    {avatarDefinition.groups.map((group) => {
      const fields = group.fields.filter((field) => !field.accessory_slot || field.choices.length > 1 || configuration.accessories[field.key] !== 'none');
      return fields.length > 0 && <fieldset key={group.id} disabled={disabled} className="space-y-3">
        <legend className="font-body font-bold text-lede text-ink-primary">{group.label}</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {fields.map((field) => {
            const scope = field.accessory_slot ? 'accessories' : 'appearance';
            const value = configuration[scope][field.key];
            return <SelectField key={field.key} label={field.label} value={value} disabled={disabled}
              onChange={(event) => onChange({ [scope]: { [field.key]: event.target.value } })}>
              {!field.choices.some((choice) => choice.value === value) && <option value={value} disabled>Unavailable saved choice</option>}
              {field.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
            </SelectField>;
          })}
        </div>
      </fieldset>;
    })}
  </div>;
}
