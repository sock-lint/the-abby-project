import { useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField } from '../../components/form';

// Deletion is an explicit, in-memory confirmation. Never restore a destructive
// intent from browser storage or retry it automatically after an interruption.
export default function DeleteMemberAccountAction({ member, remove, onRemoved }) {
  const { user: actor } = useAuth();
  const scope = `${actor?.id}:${actor?.role}:${actor?.family?.id ?? ''}:${member.id}`;
  const activeScope = useRef(scope);
  activeScope.current = scope;
  const [credential] = useState(getToken);
  const mounted = useRef(false);
  const writing = useRef(false);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const phrase = `delete ${member.username}`;
  const label = member.display_name || member.username;
  const matches = typed.trim() === phrase;
  const isCurrent = () => mounted.current && getToken() === credential && activeScope.current === scope;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const cancel = () => {
    if (writing.current) return;
    setConfirming(false);
    setTyped('');
    setError('');
  };

  const confirm = async () => {
    if (!matches || writing.current || !isCurrent()) return;
    writing.current = true;
    setBusy(true);
    setError('');
    try {
      await remove(member.id);
      if (!isCurrent()) return;
      setConfirming(false);
      setTyped('');
      onRemoved();
    } catch (failure) {
      if (!isCurrent()) return;
      setError(failure.status >= 400 && failure.status < 500
        ? failure.message
        : 'Could not confirm deletion. Try again, or cancel and refresh the member list.');
    } finally {
      writing.current = false;
      if (isCurrent()) setBusy(false);
    }
  };

  return <>
    <Button type="button" variant="danger" size="sm" disabled={busy}
      className="flex items-center justify-center gap-1.5"
      onClick={() => { if (isCurrent()) setConfirming(true); }}>
      <Trash2 size={14} aria-hidden="true" /> Delete account
    </Button>
    {confirming && <BottomSheet title={`Delete ${label}'s account?`} onClose={cancel} disabled={busy}>
      <div className="space-y-3" aria-busy={busy}>
        <p className="text-body text-ink-secondary">
          This permanently deletes <strong>{label}</strong>’s account, private journal,
          related account records and saved connections. Projects and homework they created or were assigned
          are also deleted, including contributions from other people. This cannot be undone.
        </p>
        <p className="text-body text-ink-secondary">
          Activity summaries and other family members’ records may still contain their name or shared text.
          Stored files are queued for deletion with retries if cleanup fails.
          Backups, versioned storage copies and copies held by connected providers may remain.
        </p>
        <ErrorAlert message={error} />
        <p className="text-body text-ink-whisper">
          To confirm, type <code className="px-1 bg-ink-page-shadow/60 rounded">{phrase}</code> below.
        </p>
        <TextField label="Type to confirm" value={typed} disabled={busy}
          onChange={(event) => setTyped(event.target.value)} autoComplete="off" />
        <div className="flex gap-2 justify-end pt-2">
          <Button type="button" variant="secondary" onClick={cancel} disabled={busy}>Cancel</Button>
          <Button type="button" variant="danger" disabled={!matches || busy} onClick={confirm}>
            {busy ? 'Deleting…' : 'Delete account'}
          </Button>
        </div>
      </div>
    </BottomSheet>}
  </>;
}
