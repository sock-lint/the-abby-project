import { useState } from 'react';
import { createReward, getItemCatalog, updateReward } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import { useApi } from '../../hooks/useApi';
import { formLabelClass } from '../../constants/styles';
import Button from '../../components/Button';
import { TextField, SelectField, TextAreaField } from '../../components/form';
import { downscaleImage } from '../../utils/image';
import { normalizeList } from '../../utils/api';

const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const FULFILLMENT_KINDS = [
  { value: 'real_world', label: 'Real-world reward' },
  { value: 'digital_item', label: 'Digital item' },
  { value: 'both', label: 'Both' },
];

export default function RewardFormModal({ reward, onClose, onSaved }) {
  const isEdit = !!reward;
  const { data: itemCatalogData } = useApi(getItemCatalog);
  const itemCatalog = normalizeList(itemCatalogData);
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: reward?.name || '',
    description: reward?.description || '',
    icon: reward?.icon || '',
    cost_coins: reward?.cost_coins ?? '',
    rarity: reward?.rarity || 'common',
    stock: reward?.stock ?? '',
    requires_parent_approval: reward?.requires_parent_approval ?? true,
    is_active: reward?.is_active ?? true,
    order: reward?.order ?? 0,
    fulfillment_kind: reward?.fulfillment_kind || 'real_world',
    item_definition: reward?.item_definition || '',
  });
  const [imageFile, setImageFile] = useState(null);

  const onField = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    set({ [k]: val });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('name', form.name);
      fd.append('description', form.description);
      fd.append('icon', form.icon);
      fd.append('cost_coins', parseInt(form.cost_coins) || 0);
      fd.append('rarity', form.rarity);
      if (form.stock !== '' && form.stock !== null) fd.append('stock', parseInt(form.stock));
      fd.append('requires_parent_approval', form.requires_parent_approval);
      fd.append('is_active', form.is_active);
      fd.append('order', parseInt(form.order) || 0);
      fd.append('fulfillment_kind', form.fulfillment_kind);
      if (form.fulfillment_kind !== 'real_world') {
        fd.append('item_definition', form.item_definition);
      } else {
        fd.append('item_definition', '');
      }
      if (imageFile) fd.append('image', await downscaleImage(imageFile));
      if (isEdit) await updateReward(reward.id, fd);
      else await createReward(fd);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={isEdit ? 'Edit Reward' : 'New Reward'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon (emoji)" value={form.icon} onChange={onField('icon')} placeholder="🎁" />
          <TextField label="Cost (coins)" type="number" min="0" value={form.cost_coins} onChange={onField('cost_coins')} required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Rarity" value={form.rarity} onChange={onField('rarity')}>
            {RARITIES.map((r) => (
              <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
            ))}
          </SelectField>
          <TextField label="Stock (blank = unlimited)" type="number" min="0" value={form.stock} onChange={onField('stock')} placeholder="∞" />
        </div>
        <div>
          <label className={formLabelClass}>Image</label>
          {/* Raw <input type="file"> stays — file picker visual is intentionally different from inputClass */}
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setImageFile(e.target.files[0])}
            className="text-sm text-ink-primary"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Order" type="number" value={form.order} onChange={onField('order')} />
          <SelectField
            label="Fulfillment"
            value={form.fulfillment_kind}
            onChange={(e) => {
              const fulfillmentKind = e.target.value;
              set({
                fulfillment_kind: fulfillmentKind,
                item_definition: fulfillmentKind === 'real_world' ? '' : form.item_definition,
              });
            }}
          >
            {FULFILLMENT_KINDS.map((kind) => (
              <option key={kind.value} value={kind.value}>{kind.label}</option>
            ))}
          </SelectField>
        </div>
        {form.fulfillment_kind !== 'real_world' && (
          <SelectField
            label="Inventory item"
            value={form.item_definition}
            onChange={onField('item_definition')}
            required
            helpText="The selected item is added to the child's Satchel when the reward is fulfilled."
          >
            <option value="">Choose an item…</option>
            {itemCatalog.map((item) => (
              <option key={item.id} value={item.id}>
                {item.icon || '🎁'} {item.name} · {item.type_display || item.item_type}
              </option>
            ))}
          </SelectField>
        )}
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.requires_parent_approval}
              onChange={onField('requires_parent_approval')}
              className="accent-amber-primary"
            />
            Requires approval
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={onField('is_active')}
              className="accent-amber-primary"
            />
            Active
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-whisper hover:text-ink-primary">
            Cancel
          </button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}
