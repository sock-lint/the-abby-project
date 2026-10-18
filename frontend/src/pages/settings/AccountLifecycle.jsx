import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { getAccountLifecycle, transferFamilyContact, deleteOwnAccount, closeOwnFamily } from '../../api';
import { AUTH_CHANGED_EVENT, getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import { fieldErrors } from '../../utils/api';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { SelectField, TextField } from '../../components/form';

const WORK_LABELS = {
  projects: 'Projects', project_templates: 'Project templates',
  homework_assignments: 'Homework assignments', homework_templates: 'Homework templates',
  chores: 'Chores', habits: 'Habits',
};
const CHILD_SHARED_WORK = ['homework_assignments', 'chores', 'habits'];
let nextCredentialVersion = 0;

function subscribeCredential(onChange) {
  window.addEventListener(AUTH_CHANGED_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

function readPreview(data, user) {
  if (data?.user?.id !== user.id || data.user.username !== user.username
    || data.family?.id !== user.family.id || typeof data.family.name !== 'string'
    || typeof data.family.slug !== 'string' || !data.family.slug
    || typeof data.family_version !== 'string' || !/^[a-f0-9]{64}$/.test(data.family_version)
    || !Array.isArray(data.successors)
    || data.successors.some((parent) => !Number.isInteger(parent.id) || parent.id === user.id || typeof parent.display_name !== 'string')
    || new Set(data.successors.map(({ id }) => id)).size !== data.successors.length
    || Object.keys(WORK_LABELS).some((key) => !Number.isInteger(data.shared_work?.[key]) || data.shared_work[key] < 0)
    || (data.family_members && ['parents', 'children'].some((key) => !Number.isInteger(data.family_members[key]) || data.family_members[key] < 0))
    || typeof data.can_delete_account !== 'boolean' || typeof data.can_close_family !== 'boolean') {
    throw new Error('The account deletion preview could not be verified.');
  }
  return data;
}

export default function AccountLifecycle() {
  const { user } = useAuth();
  const credential = useSyncExternalStore(subscribeCredential, getToken, getToken);
  // Reuse the settings form's opaque credential-version pattern: no passwords,
  // tokens or destructive confirmations are saved in React keys or storage.
  const credentialVersion = useMemo(() => credential ? ++nextCredentialVersion : 'anonymous', [credential]);
  if (!user?.id || !user.family?.id || !credential) return null;
  return <LifecyclePanel key={`${user.id}:${user.role}:${user.family.id}:${credentialVersion}`} user={user} />;
}

function LifecyclePanel({ user }) {
  const [credential] = useState(getToken);
  const identity = useMemo(() => ({ id: user.id, username: user.username, family: { id: user.family.id } }),
    [user.id, user.username, user.family.id]);
  const mounted = useRef(false);
  const requestId = useRef(0);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState('');
  const isParent = user.role === 'parent';

  const load = useCallback(async () => {
    const current = ++requestId.current;
    const isCurrent = () => mounted.current && getToken() === credential && current === requestId.current;
    if (!isCurrent()) return;
    setLoading(true);
    setError('');
    setPreview(null);
    try {
      const next = readPreview(await getAccountLifecycle({ token: credential }), identity);
      if (isCurrent()) setPreview(next);
    } catch {
      if (isCurrent()) setError('Could not load your account deletion options. Try again.');
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, [credential, identity]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; requestId.current += 1; };
  }, [load]);

  const canDelete = preview?.can_delete_account && (!isParent || preview.successors.length > 0);
  const hasChildSharedWork = user.role === 'child' && CHILD_SHARED_WORK.some((key) => preview?.shared_work[key] > 0);
  return <section className="mt-4 pt-4 border-t border-ink-page-shadow space-y-3" aria-label="Account deletion and family handoff">
    <h3 className="font-body font-semibold text-ink-primary">Account deletion and family handoff</h3>
    {loading && <p role="status" className="text-body text-ink-secondary">Loading account deletion options…</p>}
    {error && <><ErrorAlert message={error} /><Button variant="secondary" onClick={load}>Retry account options</Button></>}
    {message && <p role="status" className="text-body text-sheikah-teal-deep">{message}</p>}
    {preview && !loading && <>
      <p className="text-body text-ink-secondary">Review what will be kept or deleted before confirming with your current password.</p>
      <div className="flex flex-wrap gap-3">
        {isParent && preview.successors.length > 0 && <Button variant="secondary" onClick={() => setMode('transfer')}>Transfer family contact</Button>}
        <Button variant="danger" disabled={!canDelete} onClick={() => setMode('delete')}>Delete my account</Button>
        {isParent && <Button variant="danger" disabled={!preview.can_close_family} onClick={() => setMode('close')}>Close family</Button>}
        <Button variant="ghost" onClick={load}>Refresh account options</Button>
      </div>
      {isParent && !canDelete && <p className="text-caption text-ink-secondary">To leave this family, another active parent must keep the shared work. If you are the last active parent, you can close the whole family instead.</p>}
      {!canDelete && hasChildSharedWork && <p className="text-caption text-ink-secondary">An active family parent is needed to keep your shared work before you can delete your account. Ask a family parent or operator for help, then refresh these options.</p>}
      {isParent && !preview.can_close_family && <p className="text-caption text-ink-secondary">Only the last active parent can close the family.</p>}
      {mode && <LifecycleConfirmation key={mode} mode={mode} user={user} preview={preview} credential={credential}
        onCancel={() => setMode('')}
        onRefresh={() => { setMode(''); void load(); }}
        onTransferred={() => {
          setMode('');
          setMessage('Family contact updated. Every parent still has the same access.');
          void load();
        }} />}
    </>}
  </section>;
}

function LifecycleConfirmation({ mode, user, preview, credential, onCancel, onRefresh, onTransferred }) {
  const { signOutDeletedAccount } = useAuth();
  const mounted = useRef(false);
  const writing = useRef(false);
  const [password, setPassword] = useState('');
  const [successor, setSuccessor] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [familyChanged, setFamilyChanged] = useState(false);
  const [errors, setErrors] = useState({});
  const transfer = mode === 'transfer';
  const close = mode === 'close';
  const needsSuccessor = transfer || (!close && user.role === 'parent');
  const childSharedWork = user.role === 'child' ? CHILD_SHARED_WORK.filter((key) => preview.shared_work[key] > 0) : [];
  const phrase = close ? preview.family.slug : preview.user.username;
  const title = transfer ? 'Transfer family contact' : close ? `Close ${preview.family.name}?` : 'Delete my account?';
  const action = transfer ? 'Transfer family contact' : close ? 'Close family permanently' : 'Delete my account permanently';
  const selectedParent = preview.successors.find(({ id }) => String(id) === successor);
  const ready = Boolean(!familyChanged && password && (!needsSuccessor || selectedParent) && (transfer || confirmation === phrase));
  const isCurrent = () => mounted.current && getToken() === credential;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    if (!ready || writing.current || !isCurrent()) return;
    writing.current = true;
    setBusy(true);
    setError('');
    setErrors({});
    try {
      const options = { token: credential };
      if (transfer) await transferFamilyContact({ password, successor_id: selectedParent.id }, options);
      else if (close) await closeOwnFamily({ password, confirm_family_slug: confirmation, family_version: preview.family_version }, options);
      else await deleteOwnAccount({ password, confirm_username: confirmation, ...(needsSuccessor ? { successor_id: selectedParent.id } : {}) }, options);
      if (!isCurrent()) return;
      setPassword('');
      if (transfer) onTransferred();
      else signOutDeletedAccount(credential);
    } catch (failure) {
      if (isCurrent()) {
        if (close && failure.status === 409) setFamilyChanged(true);
        const fields = Object.fromEntries(Object.entries(fieldErrors(failure))
          .filter(([key]) => ['password', 'successor_id', 'confirm_username', 'confirm_family_slug'].includes(key)));
        setErrors(fields);
        if (!Object.keys(fields).length) setError(failure.status >= 400 && failure.status < 500
          ? failure.message : 'Could not confirm this change. Your form is still here. Retry deliberately, or cancel and reload your account options.');
      }
    } finally {
      writing.current = false;
      if (isCurrent()) setBusy(false);
    }
  };

  return <BottomSheet title={title} onClose={() => { if (!writing.current) onCancel(); }} disabled={busy}>
    <form onSubmit={submit} className="space-y-3" aria-busy={busy}>
      {transfer ? <p className="text-body text-ink-secondary">Choose which parent is listed as the family contact. This gives no extra access: all parents keep equal permissions. Your account, shared work and private journal stay where they are.</p>
        : close ? <>
          <p className="text-body text-ink-secondary">This permanently deletes the family, every child and inactive parent account, private journals, shared work and family settings, including saved provider and printer credentials. Your account is deleted too. This cannot be undone.</p>
          {preview.family_members && <p className="text-body text-ink-secondary">Accounts affected: {preview.family_members.parents} {preview.family_members.parents === 1 ? 'parent' : 'parents'} and {preview.family_members.children} {preview.family_members.children === 1 ? 'child' : 'children'}, including inactive accounts.</p>}
        </> : <>
          <p className="text-body text-ink-secondary">This permanently deletes your account, private journal, personal records and saved connections. Projects and homework assigned to you and your personal habits are deleted. This cannot be undone.</p>
          {childSharedWork.length > 0 && <>
            <p className="text-body text-ink-secondary">An active family parent will keep this shared work automatically. Other family members’ history and rewards for it stay with your family. Your own assignments, submissions, logs and private journal are still deleted and are never transferred.</p>
            <dl className="grid grid-cols-2 gap-2 text-caption" aria-label="Shared work kept for your family">
              {childSharedWork.map((key) => <div key={key}><dt className="text-ink-secondary">{WORK_LABELS[key]}</dt><dd className="font-semibold">{preview.shared_work[key]}</dd></div>)}
            </dl>
          </>}
          {needsSuccessor && <p className="text-body text-ink-secondary">Shared work you created for surviving members, including projects, homework, templates, chores and habits, moves to the parent you choose. Your private journal never transfers. Family settings stay with the family.</p>}
          {needsSuccessor && <dl className="grid grid-cols-2 gap-2 text-caption" aria-label="Shared work to hand off">
            {Object.entries(WORK_LABELS).map(([key, label]) => <div key={key}><dt className="text-ink-secondary">{label}</dt><dd className="font-semibold">{preview.shared_work[key]}</dd></div>)}
          </dl>}
        </>}
      {!transfer && <p className="text-body text-ink-secondary">Retained activity summaries or other members’ records may still contain your name or shared text. Files on deleted records are queued for deletion with retries. Backups, versioned storage, provider copies and device downloads may remain. Google grants and exported files must be removed with Google separately.</p>}
      <ErrorAlert message={error} />
      {familyChanged && <><p className="text-body text-ink-secondary">Review the latest family details before trying closure again.</p><Button variant="secondary" onClick={onRefresh}>Review updated family</Button></>}
      {needsSuccessor && <SelectField label={transfer ? 'New family contact' : 'Parent to keep shared work'} value={successor} disabled={busy} error={errors.successor_id}
        onChange={(event) => setSuccessor(event.target.value)}>
        <option value="">Choose an active parent</option>
        {preview.successors.map((parent) => <option key={parent.id} value={parent.id}>{parent.display_name}</option>)}
      </SelectField>}
      <TextField label="Current password" type="password" value={password} disabled={busy} error={errors.password}
        helpText="Use your Abby password. If you do not have an Abby password, ask a family parent or operator for a password reset first."
        autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
      {!transfer && <>
        <p className="text-body text-ink-secondary">To confirm, type <code>{phrase}</code>.</p>
        <TextField label={close ? 'Type the family identifier to confirm' : 'Type your username to confirm'} value={confirmation} disabled={busy}
          error={close ? errors.confirm_family_slug : errors.confirm_username} autoComplete="off" onChange={(event) => setConfirmation(event.target.value)} />
      </>}
      <div className="flex flex-wrap justify-end gap-3">
        <Button variant="secondary" disabled={busy} onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant={transfer ? 'primary' : 'danger'} disabled={!ready || busy}>{busy ? 'Confirming…' : action}</Button>
      </div>
    </form>
  </BottomSheet>;
}
