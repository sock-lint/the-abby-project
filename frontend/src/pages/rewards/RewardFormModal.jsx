import { useId, useState } from 'react';
import { createReward, getItemCatalog, updateReward } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import { useApi } from '../../hooks/useApi';
import { formLabelClass } from '../../constants/styles';
import ModalActions from '../../components/ModalActions';
import { TextField, SelectField, TextAreaField, CheckboxField, IconPicker } from '../../components/form';
import { downscaleImage } from '../../utils/image';
import { normalizeList } from '../../utils/api';
import { isCatalogAvailable } from '../../utils/catalogAvailability';
import RewardPriceGuide from '../../components/rewards/RewardPriceGuide';

const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const FULFILLMENT_KINDS = [
  { value: 'real_world', label: 'Real-world reward' },
  { value: 'digital_item', label: 'Digital item' },
  { value: 'both', label: 'Both' },
];

function pouchCoinAmount(item) {
  const metadata = item?.metadata;
  if (metadata && (typeof metadata !== 'object' || Array.isArray(metadata))) return null;
  // Match pouch opening: a false/zero metadata value falls back to coin_value;
  // numeric strings must be integers, while numeric values truncate toward zero.
  const value = metadata?.coins || item?.coin_value || 0;
  if (typeof value !== 'number' && typeof value !== 'boolean'
      && (typeof value !== 'string' || !/^[+-]?\d+$/.test(value.trim()))) return null;
  const coins = Math.trunc(Number(value));
  return Number.isSafeInteger(coins) && coins > 0 ? coins : null;
}

export default function RewardFormModal({ reward, onClose, onSaved }) {
  const isEdit = !!reward;
  const imageId = useId();
  const { data: itemCatalogData } = useApi(getItemCatalog);
  const itemCatalog = normalizeList(itemCatalogData).filter(isCatalogAvailable);
  const { form, set, saving, setSaving, error, setError, dirty } = useFormState({
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
  const selectedItem = itemCatalog.find((item) => String(item.id) === String(form.item_definition));
  const pouchCoins = selectedItem?.item_type === 'coin_pouch' ? pouchCoinAmount(selectedItem) : null;
  // This form saves parseInt(cost_coins), including exponent-form number input.
  const submittedCost = parseInt(form.cost_coins);
  const warnPouchGain = form.fulfillment_kind !== 'real_world'
    && (form.stock === '' || form.stock === null)
    && Number.isSafeInteger(submittedCost) && submittedCost >= 0
    && pouchCoins !== null && pouchCoins > submittedCost;

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
      // DRF accepts an empty multipart field as null; omitting it on PATCH
      // would leave the previous finite stock unchanged.
      fd.append('stock', form.stock === '' || form.stock === null ? '' : parseInt(form.stock));
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
    <BottomSheet title={isEdit ? 'Edit reward' : 'New reward'} onClose={onClose} dirty={dirty}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <IconPicker label="Icon (emoji)" value={form.icon} onChange={(icon) => set({ icon })} placeholder="🎁" disabled={saving} />
        <TextField label="Cost (coins)" type="number" min="0" value={form.cost_coins} onChange={onField('cost_coins')} required disabled={saving} />
        <RewardPriceGuide onApply={(cost_coins) => set({ cost_coins })} disabled={saving} />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SelectField label="Rarity" value={form.rarity} onChange={onField('rarity')}>
            {RARITIES.map((r) => (
              <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
            ))}
          </SelectField>
          <TextField label="Stock (blank = unlimited)" type="number" min="0" value={form.stock} onChange={onField('stock')} placeholder="∞" />
        </div>
        <div>
          <label htmlFor={imageId} className={formLabelClass}>Image</label>
          {/* Raw <input type="file"> stays — file picker visual is intentionally different from inputClass */}
          <input
            id={imageId}
            type="file"
            accept="image/*"
            onChange={(e) => setImageFile(e.target.files[0])}
            className="text-sm text-ink-primary"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
            helpText="The selected item is added to the child's inventory when the reward is fulfilled."
          >
            <option value="">Choose an item…</option>
            {itemCatalog.map((item) => (
              <option key={item.id} value={item.id}>
                {item.icon || '🎁'} {item.name} · {item.type_display || item.item_type}
              </option>
            ))}
          </SelectField>
        )}
        {warnPouchGain && (
          <p role="status" className="rounded-lg border border-ink-page-shadow p-3 text-caption text-ink-secondary">
            This unlimited offer costs {submittedCost} Coins and its pouch pays {pouchCoins} Coins, a net gain of {pouchCoins - submittedCost} Coins per purchase. You can still save this offer.
          </p>
        )}
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          <CheckboxField
            label="Requires approval"
            checked={form.requires_parent_approval}
            onChange={onField('requires_parent_approval')}
          />
          <CheckboxField
            label="Active"
            checked={form.is_active}
            onChange={onField('is_active')}
          />
        </div>
        <ModalActions
          onClose={onClose}
          saving={saving}
          submitLabel={isEdit ? 'Update' : 'Create'}
        />
      </form>
    </BottomSheet>
  );
}
