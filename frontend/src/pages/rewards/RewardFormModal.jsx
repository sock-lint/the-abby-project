import { useState } from 'react';
import { createReward, updateReward } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';
import { downscaleImage } from '../../utils/image';

const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];

export default function RewardFormModal({ reward, onClose, onSaved }) {
  const isEdit = !!reward;
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
    <FormModal title={isEdit ? 'Edit Reward' : 'New Reward'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Name</label>
          <input className={inputClass} value={form.name} onChange={onField('name')} required />
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
          <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Icon (emoji)</label>
            <input className={inputClass} value={form.icon} onChange={onField('icon')} placeholder="🎁" />
          </div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Cost (coins)</label>
            <input className={inputClass} type="number" min="0" value={form.cost_coins} onChange={onField('cost_coins')} required />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Rarity</label>
            <select className={inputClass} value={form.rarity} onChange={onField('rarity')}>
              {RARITIES.map((r) => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Stock (blank = unlimited)</label>
            <input className={inputClass} type="number" min="0" value={form.stock} onChange={onField('stock')} placeholder="∞" />
          </div>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Image</label>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setImageFile(e.target.files[0])}
            className="text-sm text-forge-text"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Order</label>
            <input className={inputClass} type="number" value={form.order} onChange={onField('order')} />
          </div>
          <div />
        </div>
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
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">
            Cancel
          </button>
          <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </FormModal>
  );
}
