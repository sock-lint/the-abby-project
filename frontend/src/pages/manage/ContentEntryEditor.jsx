import { useState } from 'react';
import Button from '../../components/Button';
import CatalogSearch from '../../components/CatalogSearch';
import SectionHeader from '../../components/SectionHeader';
import SkillTagEditor from '../../components/SkillTagEditor';
import { CheckboxField, IconPicker, SelectField, TextAreaField, TextField } from '../../components/form';
import { milestoneReferenceLabel } from './contentWorkbenchEditor';
import { isTaxonomyAvailable, taxonomyChoices, taxonomyOptionLabel } from '../../utils/taxonomy';

const labels = {
  food: 'Pet food', cosmetic_frame: 'Profile frame', cosmetic_title: 'Title',
  cosmetic_theme: 'Color theme', cosmetic_pet_accessory: 'Pet accessory',
  coin_pouch: 'Coin pouch', quest_scroll: 'Challenge scroll', consumable: 'Consumable',
  egg: 'Pet egg', potion: 'Hatching potion', boss: 'Boss challenge', collection: 'Activity count',
};
const title = (value) => labels[value] ?? String(value).replaceAll('_', ' ');
const choiceValue = (choice) => typeof choice === 'string' ? choice : Array.isArray(choice) ? choice[0] : choice.value;
const choiceLabel = (choice) => typeof choice === 'string' ? title(choice) : Array.isArray(choice) ? choice[1] : choice.label ?? title(choice.value);

export default function ContentEntryEditor({ editor, onChange, catalog, rules, busy, canSave, error, onSave, onDiscard, onVersion, onRemove, source }) {
  const [itemSearch, setItemSearch] = useState('');
  const { values, section, object_id } = editor;
  const set = (field, value) => onChange({ ...editor, values: { ...values, [field]: value } });
  const numeric = (field, label, min = 0) => <TextField label={label} type="number" min={min} max={field === 'duration_days' ? 365 : 1000000} step="1" required value={values[field] ?? 0} onChange={(event) => set(field, event.target.value === '' ? '' : Number(event.target.value))} />;
  const editable = source?.editable !== false;
  const availableTriggers = values.quest_type === 'boss' ? rules.boss_triggers ?? rules.triggers : rules.triggers;
  const supportedTriggers = new Map((availableTriggers ?? []).map((choice) => [choiceValue(choice), choice]));
  let hasAdditionalFilters = true;
  try {
    const additionalFilters = JSON.parse(editor.filterText);
    hasAdditionalFilters = !additionalFilters || typeof additionalFilters !== 'object' || Array.isArray(additionalFilters) || Object.keys(additionalFilters).length > 0;
  } catch { /* Invalid filters must be corrected before enabling untimed challenges. */ }
  const selectedTriggers = Array.isArray(values.trigger_filter?.allowed_triggers) ? values.trigger_filter.allowed_triggers : [];
  const canBeUntimed = values.quest_type === 'collection' && !values.is_repeatable && !values.is_cooperative
    && selectedTriggers.length === 1 && selectedTriggers[0] === 'reading_logged' && !hasAdditionalFilters;
  const triggerChoices = [...new Set([...supportedTriggers.keys(), ...selectedTriggers])];
  const rewardItems = values.reward_items ?? [];
  const itemIdentity = (item) => item.id ? `id:${item.id}` : `new:${item.key}`;
  const rewardIdentity = (reward) => reward.item_id ? `id:${reward.item_id}` : `new:${reward.item_key}`;
  const matchingItems = catalog.items.filter((item) => `${item.name} ${item.slug ?? ''}`.toLowerCase().includes(itemSearch.toLowerCase()));
  const prerequisiteChoices = (catalog.quests ?? []).filter((quest) => quest.id && quest.id !== object_id && quest.is_system !== false);
  const selectedPrerequisiteListed = prerequisiteChoices.some((quest) => quest.id === values.prerequisite_quest);
  const selectedSkillListed = catalog.skills.some((skill) => skill.id === values.required_skill);
  const addItem = () => {
    const item = matchingItems.find((candidate) => !rewardItems.some((reward) => rewardIdentity(reward) === itemIdentity(candidate)));
    if (item) set('reward_items', [...rewardItems, { ...(item.id ? { item_id: item.id } : { item_key: item.key }), quantity: 1 }]);
  };

  return <form aria-label={section === 'quests' ? 'Challenge editor' : 'Item editor'} onSubmit={(event) => { event.preventDefault(); onSave(); }} className="space-y-4">
    <SectionHeader as="h3" title={`${object_id ? 'Edit' : 'New'} ${section === 'quests' ? 'challenge' : 'item'}`}>{!editable ? source.edit_reason : canSave ? 'Save changes to your draft, then review and simulate them before publication.' : 'Create or open an unpublished draft to edit this content.'}</SectionHeader>
    <fieldset disabled={busy || !editable || !canSave} className="min-w-0 space-y-4">
      <legend className="sr-only">Content details</legend>
      <TextField label="Name" value={values.name ?? ''} maxLength="100" required onChange={(event) => set('name', event.target.value)} />
      <TextAreaField label="Description" value={values.description ?? ''} maxLength="10000" required={section === 'quests'} onChange={(event) => set('description', event.target.value)} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <IconPicker label="Icon" value={values.icon ?? ''} maxLength={50} onChange={(value) => set('icon', value)} disabled={busy || !editable} />
        <TextField label="Artwork key" value={values.sprite_key ?? ''} maxLength="64" onChange={(event) => set('sprite_key', event.target.value)} helpText="Use an existing registered artwork identity. An icon remains the fallback." />
      </div>
      {section === 'items' ? <>
        {object_id ? <p className="text-caption text-ink-secondary">Stable identity: {source?.slug || `item ${object_id}`} · {title(source?.item_type)}</p> : <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TextField label="Stable item key" value={values.slug ?? ''} maxLength="100" required pattern="[a-zA-Z0-9_-]+" onChange={(event) => set('slug', event.target.value)} helpText="A unique permanent key, such as forest-snack." />
          <SelectField label="Item type" value={values.item_type} onChange={(event) => set('item_type', event.target.value)}>{(rules.create_item_types ?? rules.item_types ?? ['food', 'cosmetic_frame', 'cosmetic_title', 'coin_pouch', 'consumable']).filter((choice) => !['egg', 'potion'].includes(choiceValue(choice))).map((choice) => <option key={choiceValue(choice)} value={choiceValue(choice)}>{choiceLabel(choice)}</option>)}</SelectField>
        </div>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SelectField label="Rarity" value={values.rarity ?? source?.rarity} disabled={Boolean(object_id)} onChange={(event) => set('rarity', event.target.value)}>{(rules.rarities ?? ['common', 'uncommon', 'rare', 'epic', 'legendary']).map((choice) => <option key={choiceValue(choice)} value={choiceValue(choice)}>{choiceLabel(choice)}</option>)}</SelectField>
          {object_id ? <TextField label="Coin value" type="number" value={source?.coin_value ?? 0} disabled /> : numeric('coin_value', 'Coin value')}
        </div>
        {object_id && <p className="text-caption text-ink-secondary">Rarity, value and effects are preserved for items already owned or promised. Create a new item version to change behavior, then choose that version in future challenge rewards.</p>}
        <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Advanced item properties</summary><TextAreaField label="Item properties (JSON)" rows={6} value={editor.metadataText} disabled={Boolean(object_id)} onChange={(event) => onChange({ ...editor, metadataText: event.target.value })} helpText="Type-specific effect properties. Publication validates supported behavior." /></details>
      </> : <>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <SelectField label="Challenge type" value={values.quest_type} onChange={(event) => set('quest_type', event.target.value)}><option value="collection">Activity count</option><option value="boss">Boss challenge</option></SelectField>
          {numeric('target_value', values.quest_type === 'boss' ? 'Target damage' : 'Target count', 1)}
          {values.duration_days !== null && numeric('duration_days', 'Duration in days', 1)}
        </div>
        <CheckboxField label="No deadline" checked={values.duration_days === null} disabled={!canBeUntimed && values.duration_days !== null} onChange={(event) => onChange({
          ...editor,
          timedDurationDays: values.duration_days ?? editor.timedDurationDays,
          values: { ...values, duration_days: event.target.checked ? null : editor.timedDurationDays ?? 7 },
        })} helpText="Available for one-time activity count challenges that count only daily Reading Adventures. Saved goals keep their original completion windows." />
        <CheckboxField label="Repeatable challenge" checked={values.is_repeatable ?? false} onChange={(event) => set('is_repeatable', event.target.checked)} />
        <CheckboxField label="Shared family challenge" checked={values.is_cooperative ?? false} onChange={(event) => set('is_cooperative', event.target.checked)} helpText="A parent selects at least two children to work toward one shared target. Each participant receives the full completion reward." />
        <SelectField label="Required badge" value={values.required_badge ?? ''} onChange={(event) => set('required_badge', event.target.value ? Number(event.target.value) : null)}><option value="">No badge required</option>{catalog.badges.map((badge) => <option key={badge.id} value={badge.id}>{badge.name}</option>)}</SelectField>
        <section aria-label="Challenge milestones" className="space-y-3 rounded-lg bg-ink-page-aged p-3">
          <h4 className="font-semibold text-ink-primary">Milestones before a new offer</h4>
          <p className="text-caption text-ink-secondary">Every selected milestone and the required badge must be met before a new challenge is offered. Saved goals keep their accepted progress and completion windows.</p>
          <p className="text-caption text-ink-secondary">Milestone gates currently support daily Reading Adventures: use an activity count challenge with Reading logged as its only qualifying activity and no additional activity filters.</p>
          <SelectField label="Previous challenge" value={values.prerequisite_quest ?? ''} onChange={(event) => set('prerequisite_quest', event.target.value === '' ? null : Number(event.target.value))} helpText="Require a completion of this exact catalog challenge. This is separate from the new challenge’s qualifying activities.">
            <option value="">No previous challenge required</option>
            {values.prerequisite_quest && !selectedPrerequisiteListed && <option value={values.prerequisite_quest} disabled>{source?.prerequisite_quest_name || 'Retained challenge'} (#{values.prerequisite_quest}) · not listed</option>}
            {prerequisiteChoices.map((quest) => <option key={quest.id} value={quest.id}>{milestoneReferenceLabel(quest, catalog.quests)}</option>)}
          </SelectField>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SelectField label="Required skill" value={values.required_skill ?? ''} onChange={(event) => {
              const skill = event.target.value === '' ? null : Number(event.target.value);
              onChange({ ...editor, values: { ...values, required_skill: skill, required_skill_level: skill === null ? 0 : Math.max(1, values.required_skill_level || 1) } });
            }} helpText="Use a named skill’s attained level. XP reward tags below do not create this requirement.">
              <option value="">No skill required</option>
              {values.required_skill && !selectedSkillListed && <option value={values.required_skill} disabled>{source?.required_skill_name || 'Retained skill'} (#{values.required_skill}) · not listed</option>}
              {taxonomyChoices(catalog.skills, values.required_skill).map((skill) => <option key={skill.id} value={skill.id} disabled={!isTaxonomyAvailable(skill)}>{skill.category_name ? `${skill.category_name} / ` : ''}{taxonomyOptionLabel(skill, milestoneReferenceLabel(skill, catalog.skills))}</option>)}
            </SelectField>
            <TextField label="Required skill level" type="number" min="1" max="6" step="1" required={Boolean(values.required_skill)} disabled={!values.required_skill} value={values.required_skill_level ?? 0} onChange={(event) => set('required_skill_level', event.target.value === '' ? '' : Number(event.target.value))} helpText="Levels 1 to 6. Clearing the skill removes the level requirement." />
          </div>
        </section>
        <fieldset className="space-y-2"><legend className="font-semibold text-ink-primary">Qualifying activities</legend><p className="text-caption text-ink-secondary">Leave all unchecked to use the default everyday activities.</p><div className="grid grid-cols-1 sm:grid-cols-2 gap-2">{triggerChoices.map((trigger) => {
          const label = supportedTriggers.has(trigger) ? choiceLabel(supportedTriggers.get(trigger)) : `${title(trigger)} · not tracked by current challenges`;
          return <CheckboxField key={trigger} label={label} checked={selectedTriggers.includes(trigger)} onChange={(event) => set('trigger_filter', { ...values.trigger_filter, allowed_triggers: event.target.checked ? [...selectedTriggers, trigger] : selectedTriggers.filter((entry) => entry !== trigger) })} />;
        })}</div></fieldset>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{numeric('coin_reward', 'Coin reward')}{numeric('xp_reward', 'XP reward')}</div>
        <div className="[&_li]:flex-wrap [&_li>div:first-child]:min-w-0 [&_li>div:first-child]:basis-full sm:[&_li>div:first-child]:basis-auto"><SkillTagEditor skills={catalog.skills} value={values.skill_tags ?? []} onChange={(tags) => set('skill_tags', tags)} /></div>
        <section className="space-y-3" aria-label="Challenge item rewards">
          <h4 className="font-semibold text-ink-primary">Item rewards</h4>
          <CatalogSearch ariaLabel="Search reward items" placeholder="Find an item…" value={itemSearch} onChange={setItemSearch} />
          <ul className="space-y-3">{rewardItems.map((reward, index) => {
            const selected = rewardIdentity(reward);
            const options = catalog.items.filter((item) => itemIdentity(item) === selected || matchingItems.includes(item));
            return <li key={index} className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_6rem_auto] gap-2 items-end">
              <SelectField label={`Reward item ${index + 1}`} value={selected} onChange={(event) => {
                const [kind, identity] = event.target.value.split(':');
                set('reward_items', rewardItems.map((entry, position) => position === index ? { ...(kind === 'id' ? { item_id: Number(identity) } : { item_key: identity }), quantity: entry.quantity } : entry));
              }}>{options.map((item) => <option key={itemIdentity(item)} value={itemIdentity(item)} disabled={rewardItems.some((other, position) => position !== index && rewardIdentity(other) === itemIdentity(item))}>{item.name}{item.runtime_available === false ? ' · unavailable' : item.id ? '' : ' · draft'}</option>)}</SelectField>
              <TextField label={`Quantity ${index + 1}`} type="number" min="1" max="1000" required value={reward.quantity} onChange={(event) => set('reward_items', rewardItems.map((entry, position) => position === index ? { ...entry, quantity: event.target.value === '' ? '' : Number(event.target.value) } : entry))} />
              <Button variant="ghost" aria-label={`Remove reward item ${index + 1}`} onClick={() => set('reward_items', rewardItems.filter((_, position) => position !== index))}>Remove</Button>
            </li>;
          })}</ul>
          <Button variant="secondary" onClick={addItem} disabled={!matchingItems.some((item) => !rewardItems.some((reward) => rewardIdentity(reward) === itemIdentity(item)))}>Add reward item</Button>
        </section>
        <details><summary className="min-h-11 cursor-pointer py-3 font-semibold">Advanced activity filters</summary><TextAreaField label="Additional activity filters (JSON)" rows={5} value={editor.filterText} onChange={(event) => onChange({ ...editor, filterText: event.target.value })} helpText="Other supported filters only. Choose activity triggers above." /></details>
      </>}
    </fieldset>
    {error && <p role="alert" className="text-body text-ember-deep">{error}</p>}
    <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy || !canSave || !editable}>{busy ? 'Saving…' : 'Save to draft'}</Button>{onVersion && <Button variant="secondary" disabled={busy || !canSave || !editable} onClick={onVersion}>Create new item version</Button>}{onRemove && <Button variant="ghost" disabled={busy || !canSave} onClick={onRemove}>Remove from draft</Button>}<Button variant="ghost" disabled={busy} onClick={onDiscard}>Close editor</Button></div>
  </form>;
}
