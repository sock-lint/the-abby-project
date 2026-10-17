import { useRef, useState } from 'react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { formatDateTime } from '../../utils/format';

export default function RewardDeliveryQueue({ rewards, onDeliver }) {
  const [selectedId, setSelectedId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const selected = rewards.find((row) => row.id === selectedId);
  const confirm = async () => {
    if (pending.current || !selected) return;
    pending.current = true;
    setSaving(true);
    setError('');
    try {
      await onDeliver(selected.id);
      setSelectedId(null);
    } catch (failure) {
      setError(failure.message);
    } finally {
      pending.current = false;
      setSaving(false);
    }
  };
  return <div className="space-y-3">
    <p className="text-body text-ink-secondary">Approved real-world rewards still to hand over. Confirm only after the child receives the reward.</p>
    {rewards.map((row) => <ParchmentCard key={row.id} className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0 flex-1 break-words space-y-1">
        <p className="font-body font-semibold text-body">{row.user_name} · {row.reward.name}</p>
        <p className="text-caption text-ink-secondary">{row.decided_at ? `Approved ${formatDateTime(row.decided_at)}` : 'Approved'} · {row.coin_cost_snapshot} coins</p>
        {row.reward.fulfillment_kind === 'both' && <p className="text-caption text-ink-secondary">Digital item already delivered. Real-world reward still to deliver.</p>}
        {row.parent_notes && <p className="text-body text-ink-secondary whitespace-pre-wrap">{row.parent_notes}</p>}
      </div>
      <Button variant="secondary" size="sm" onClick={() => { setError(''); setSelectedId(row.id); }}>Mark delivered</Button>
    </ParchmentCard>)}
    {selected && <BottomSheet title="Confirm reward delivery" onClose={() => setSelectedId(null)} disabled={saving}>
      <div className="space-y-3">
        <p className="text-body text-ink-primary">Confirm {selected.user_name} received {selected.reward.name}.</p>
        <p className="text-caption text-ink-secondary">This records delivery. It does not spend more coins or add another inventory item.</p>
        <ErrorAlert message={error} />
        <div className="flex justify-end gap-2 flex-wrap">
          <Button variant="ghost" onClick={() => setSelectedId(null)} disabled={saving}>Cancel</Button>
          <Button onClick={confirm} disabled={saving}>{saving ? 'Confirming…' : 'Confirm delivered'}</Button>
        </div>
      </div>
    </BottomSheet>}
  </div>;
}
