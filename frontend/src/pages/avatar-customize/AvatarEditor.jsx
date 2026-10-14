import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { saveAvatarConfiguration } from '../../api';
import { getToken } from '../../api/client';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ConfirmDialog from '../../components/ConfirmDialog';
import { SelectField } from '../../components/form';
import AvatarCustomizer from '../../components/avatar/AvatarCustomizer';
import AvatarPreview from '../../components/avatar/AvatarPreview';
import { avatarDefinition, editableConfiguration, patchConfiguration, sameConfiguration, switchAvatarConfiguration, validConfiguration } from './catalog';
import { clearAvatarDraft, readAvatarDraft, writeAvatarDraft } from './draftStore';
import useEditorViewport from './useEditorViewport';
import './avatarCustomize.css';

const DRAFT = 'avatar-configuration';

export default function AvatarEditor({ catalog, initialConfiguration, accountId, credential }) {
  const navigate = useNavigate();
  const scope = { accountId, credential };
  const [confirmed, setConfirmed] = useState(() => structuredClone(initialConfiguration));
  const [configuration, setConfiguration] = useState(() => {
    const draft = readAvatarDraft(scope, DRAFT);
    return editableConfiguration(catalog, draft) ? draft : structuredClone(initialConfiguration);
  });
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [leaving, setLeaving] = useState(false);
  const mounted = useRef(true);
  const activeScope = useRef(scope);
  const workspace = useRef(null);
  const height = useEditorViewport(workspace);
  activeScope.current = scope;
  const definition = avatarDefinition(catalog, configuration?.avatar_id);
  const changed = !sameConfiguration(confirmed, configuration);
  const editable = editableConfiguration(catalog, configuration);
  const valid = validConfiguration(catalog, configuration);
  const current = () => mounted.current && activeScope.current.accountId === accountId
    && activeScope.current.credential === credential && getToken() === credential;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!changed) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [changed]);

  const installDraft = (next) => {
    setConfiguration(next);
    if (sameConfiguration(confirmed, next)) clearAvatarDraft(scope, DRAFT);
    else writeAvatarDraft(scope, DRAFT, next);
    setError(''); setMessage('');
  };
  const update = (patch) => {
    if (!current() || working) return;
    installDraft(patchConfiguration(catalog, configuration, patch));
    setNotice('');
  };
  const changeBase = (id) => {
    if (!current() || working) return;
    const next = switchAvatarConfiguration(catalog, configuration, id);
    installDraft(next.configuration);
    setNotice(next.removed.length ? `Removed from this preview: ${next.removed.join(', ')}. Compatible accessories were kept.` : 'Compatible accessories were kept.');
  };
  const undo = () => {
    clearAvatarDraft(scope, DRAFT);
    setConfiguration(structuredClone(confirmed)); setError(''); setMessage(''); setNotice('');
  };
  const save = async () => {
    if (!changed || !valid || working || !current()) return;
    const submittedAvatarId = configuration.avatar_id;
    setWorking(true); setError(''); setMessage('');
    try {
      const result = await saveAvatarConfiguration(configuration);
      if (!current()) return;
      if (!validConfiguration(catalog, result?.avatar_configuration, submittedAvatarId)) {
        setError('Could not confirm the saved avatar. Your changes are still here. Try again.');
        return;
      }
      const saved = structuredClone(result.avatar_configuration);
      setConfirmed(saved); setConfiguration(saved);
      clearAvatarDraft(scope, DRAFT);
      setMessage('Avatar saved.'); setNotice('');
    } catch (failure) {
      if (current()) setError(failure.status === 400
        ? 'Some avatar choices could not be saved. Review your selections and try again.'
        : failure.message || 'Could not save your avatar. Try again.');
    } finally {
      if (current()) setWorking(false);
    }
  };

  return <section className="space-y-3" aria-label="Avatar customization">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Button variant="ghost" size="sm" aria-label="Back to Profile" disabled={working} onClick={() => changed ? setLeaving(true) : navigate('/profile')}
        className="inline-flex min-w-11 shrink-0 items-center justify-center gap-2"><ArrowLeft size={16} aria-hidden="true" /><span className="hidden sm:inline">Back to Profile</span></Button>
      <h1 className="font-body font-bold text-2xl text-ink-primary">Customize avatar</h1>
    </div>
    <div ref={workspace} data-avatar-workspace className="avatar-editor-workspace"
      style={height === null ? undefined : { '--avatar-editor-height': `${height}px` }}>
      <div data-avatar-preview className="avatar-editor-preview">
        <AvatarPreview configuration={configuration} avatarDefinition={definition || { id: 'unavailable', label: 'Saved', renderer_adapter: 'unavailable' }} compact
          className="avatar-editor-preview-body" stageClassName="avatar-editor-stage" />
      </div>
      <div data-avatar-controls role="region" aria-label="Avatar options" tabIndex={0} className="avatar-editor-controls rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-3">
        {!editable && <div className="space-y-3">
          <p className="font-body text-body text-ink-secondary">Your saved avatar is unavailable. Choose a prepared avatar to start a new look; your saved configuration stays unchanged until you save.</p>
          {catalog.avatars.map((avatar) => <Button key={avatar.id} variant="secondary" disabled={working} onClick={() => changeBase(avatar.id)}>Choose {avatar.label}</Button>)}
        </div>}
        {editable && catalog.avatars.length > 1 && <SelectField label="Avatar" value={configuration.avatar_id} disabled={working} className="mb-3"
          onChange={(event) => changeBase(event.target.value)}>
          {catalog.avatars.map((avatar) => <option key={avatar.id} value={avatar.id}>{avatar.label}</option>)}
        </SelectField>}
        {editable && <AvatarCustomizer avatarDefinition={definition} configuration={configuration} onChange={update} disabled={working} />}
      </div>
      <div data-avatar-actions className="avatar-editor-actions space-y-2">
        <ErrorAlert message={error} />
        {notice && <p className="font-body text-caption text-ink-secondary" role="status">{notice}</p>}
        {!valid && <p className="font-body text-caption text-ink-secondary">Some saved choices are unavailable. Choose supported replacements before saving.</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={save} disabled={!changed || !valid || working}>{working ? 'Saving…' : 'Save avatar'}</Button>
          <Button size="sm" variant="ghost" onClick={undo} disabled={!changed || working}>Undo changes</Button>
          {message && <p className="font-body text-caption text-moss-deep" role="status">{message}</p>}
        </div>
      </div>
    </div>
    {leaving && <ConfirmDialog title="Unsaved avatar changes" message="Leave without saving your changes?" confirmLabel="Discard and leave"
      onCancel={() => setLeaving(false)} onConfirm={() => { undo(); navigate('/profile'); }} />}
  </section>;
}
