import { useCallback, useId, useState } from 'react';
import { getQuestCatalog, startCoOpQuest } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import useMountedRef from '../../hooks/useMountedRef';
import { normalizeList } from '../../utils/api';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ModalActions from '../../components/ModalActions';
import RewardItem from '../../components/rpg/RewardItem';
import { CheckboxField, SelectField } from '../../components/form';
import { goalNumber } from './goalDisplay';

export default function FamilyChallengeForm({ children = [], onAssigned }) {
  const { user, isParent } = useRole();
  const token = getToken();
  // The owning Trials context verifies this roster against the current family.
  const participants = [...new Map(children.filter((child) => child.is_active !== false)
    .map((child) => [child.id, child])).values()];
  if (!isParent || participants.length < 2) return null;
  const scope = `${user.id}:${user.family?.id ?? ''}:${token}:${participants.map((child) => child.id).sort().join(',')}`;
  return <ScopedFamilyChallengeForm key={scope} children={participants} token={token} onAssigned={onAssigned} />;
}

function ScopedFamilyChallengeForm({ children, token, onAssigned }) {
  const mounted = useMountedRef();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [definitionId, setDefinitionId] = useState('');
  const [participantIds, setParticipantIds] = useState([]);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState('');
  const fetchCatalog = useCallback(() => open ? getQuestCatalog() : Promise.resolve([]), [open]);
  const { data, loading, refreshing, error, reload } = useApi(fetchCatalog, [open]);
  const catalog = normalizeList(data).filter((definition) => definition.is_cooperative === true && definition.catalog_available === true);
  const selected = catalog.find((definition) => String(definition.id) === definitionId);
  const pending = loading || refreshing;
  const toggleChild = (id) => setParticipantIds((previous) => previous.includes(id)
    ? previous.filter((value) => value !== id) : [...previous, id]);

  const assign = async (event) => {
    event.preventDefault();
    if (saving || pending || error || !selected || participantIds.length < 2 || !mounted.current || getToken() !== token) return;
    // Submit only exact identities from the same roster shown in this form.
    const userIds = children.filter((child) => participantIds.includes(child.id)).map((child) => child.id);
    if (userIds.length < 2) return;
    setSaving(true);
    setActionError('');
    try {
      await startCoOpQuest(selected.id, userIds, { token });
      if (!mounted.current || getToken() !== token) return;
      setOpen(false);
      setDefinitionId('');
      setParticipantIds([]);
      onAssigned?.();
    } catch (failure) {
      if (mounted.current && getToken() === token) setActionError(failure.message || 'Could not assign the family challenge.');
    } finally {
      if (mounted.current && getToken() === token) setSaving(false);
    }
  };

  return <>
    <Button variant="secondary" onClick={() => setOpen(true)}>Family challenges</Button>
    {open && <BottomSheet title="Assign a family challenge" onClose={() => setOpen(false)} disabled={saving} dirty footer={(
      <ModalActions formId={formId} fullWidth onClose={() => setOpen(false)} submitLabel="Assign family challenge" savingLabel="Assigning…" saving={saving} submitDisabled={pending || Boolean(error) || !selected || participantIds.length < 2} />
    )}>
      <form id={formId} onSubmit={assign} className="space-y-4">
        <p className="font-body text-body text-ink-secondary">Work together toward one shared target. Each selected child receives the full completion reward.</p>
        {pending && <p role="status" className="font-body text-caption text-ink-secondary">Loading family challenges…</p>}
        {error && <><ErrorAlert message={error} /><Button variant="secondary" disabled={pending} onClick={reload}>Retry family challenges</Button></>}
        <fieldset disabled={saving || pending || Boolean(error)} className="space-y-4 min-w-0">
          <SelectField label="Family challenge" value={definitionId} onChange={(event) => { setDefinitionId(event.target.value); setActionError(''); }} required>
            <option value="">Choose a family challenge…</option>
            {catalog.map((definition) => <option key={definition.id} value={definition.id}>{definition.name}</option>)}
          </SelectField>
          {!pending && !error && !catalog.length && <p className="font-body text-body text-ink-secondary">No family challenges are available right now.</p>}
          {selected && <section aria-label="Family challenge preview" className="space-y-2 rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3">
            <p className="font-body text-body text-ink-primary">{selected.description}</p>
            <p className="font-body text-caption text-ink-secondary">Shared target: {goalNumber(selected.target_value)} {selected.quest_type === 'boss' ? 'damage' : 'activities'} · {selected.duration_days} days</p>
            <p className="font-body text-caption text-ink-secondary">Completion reward for each child: {selected.coin_reward} coins · {selected.xp_reward} XP</p>
            {selected.reward_items?.length > 0 && <ul aria-label="Reward items for each child" className="space-y-2">
              {selected.reward_items.map((item) => <li key={item.id || item.item}><RewardItem item={item} /></li>)}
            </ul>}
          </section>}
          <fieldset className="space-y-1 min-w-0">
            <legend className="font-body font-semibold text-body text-ink-secondary">Participants</legend>
            <p className="font-body text-caption text-ink-secondary">Choose at least two children from your family.</p>
            {children.map((child) => <CheckboxField key={child.id} label={child.display_label || child.display_name || child.username} checked={participantIds.includes(child.id)} onChange={() => toggleChild(child.id)} />)}
          </fieldset>
        </fieldset>
        <ErrorAlert message={actionError} />
      </form>
    </BottomSheet>}
  </>;
}
