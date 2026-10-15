import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { getHomeworkAISettings, updateHomeworkAISettings, deleteHomeworkAISettings } from '../../api';
import { AUTH_CHANGED_EVENT, getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import { fieldErrors } from '../../utils/api';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import ConfirmDialog from '../../components/ConfirmDialog';
import { SelectField, TextField } from '../../components/form';
import { HOMEWORK_AI_PROVIDERS, HOMEWORK_AI_MODELS } from './homeworkAI.constants';

function readSettings(data) {
  if (!HOMEWORK_AI_PROVIDERS.some(({ id }) => id === data?.provider)
    || typeof data.model !== 'string' || typeof data.has_api_key !== 'boolean'
    || (data.provider === 'default' && (data.model !== '' || data.has_api_key))) {
    throw new Error('Invalid homework AI settings response');
  }
  return { provider: data.provider, model: data.model, has_api_key: data.has_api_key };
}

function subscribeToCredential(onChange) {
  window.addEventListener(AUTH_CHANGED_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

export default function HomeworkAISettings({ sectionRef }) {
  const { user } = useAuth();
  const credential = useSyncExternalStore(subscribeToCredential, getToken, getToken);
  // Keep credentials out of React keys while still resetting the form if a
  // same-account token replacement is batched with auth hydration.
  const credentialVersion = useMemo(() => credential ? crypto.randomUUID() : 'anonymous', [credential]);
  if (user?.role !== 'parent') return null;
  // Remount when the account or family changes, so a new family never inherits
  // the previous form's saved settings or in-memory API key.
  return <HomeworkAIForm key={`${user.id}:${user.family?.id ?? ''}:${credentialVersion}`} sectionRef={sectionRef} />;
}

function HomeworkAIForm({ sectionRef }) {
  const [token] = useState(getToken);
  const [saved, setSaved] = useState(null);
  const [provider, setProvider] = useState('default');
  const [modelChoice, setModelChoice] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState('loading');
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const mounted = useRef(false);
  const requestId = useRef(0);
  const writing = useRef(false);
  const model = provider === 'default' ? '' : (modelChoice === 'custom' ? customModel.trim() : modelChoice);
  const busy = status === 'saving' || status === 'removing';
  const dirty = Boolean(saved && (provider !== saved.provider || model !== saved.model || apiKey));
  usePwaUpdateGuard(dirty || busy);

  const applySettings = useCallback((settings) => {
    setSaved(settings);
    setProvider(settings.provider);
    const suggested = HOMEWORK_AI_MODELS[settings.provider]?.some(({ id }) => id === settings.model);
    setModelChoice(settings.provider === 'default' ? '' : suggested ? settings.model : 'custom');
    setCustomModel(suggested ? '' : settings.model);
    setApiKey('');
  }, []);

  const load = useCallback(async () => {
    const current = ++requestId.current;
    const isCurrent = () => mounted.current && getToken() === token && requestId.current === current;
    if (!isCurrent()) return;
    setStatus('loading');
    setLoadError('');
    try {
      const settings = readSettings(await getHomeworkAISettings());
      if (isCurrent()) applySettings(settings);
    } catch {
      if (isCurrent()) setLoadError('Could not load homework AI settings. Try again.');
    } finally {
      if (isCurrent()) setStatus('ready');
    }
  }, [applySettings, token]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [load]);

  const clearMessages = () => {
    setError('');
    setErrors({});
    setMessage('');
  };

  const changeProvider = (next) => {
    setProvider(next);
    setModelChoice(HOMEWORK_AI_MODELS[next]?.[0]?.id || '');
    setCustomModel('');
    setApiKey('');
    clearMessages();
  };

  const save = async (event) => {
    event.preventDefault();
    if (!saved || writing.current || !mounted.current || getToken() !== token) return;
    clearMessages();
    const validation = {};
    if (provider !== 'default' && !model) validation.model = 'Enter a model ID.';
    const key = apiKey.trim();
    const retainingKey = provider === saved.provider && saved.has_api_key;
    if (provider !== 'default' && !key && !retainingKey) {
      validation.api_key = 'Enter an API key for the selected provider.';
    }
    if (Object.keys(validation).length) {
      setErrors(validation);
      return;
    }
    const body = { provider, model };
    if (provider !== 'default' && key) body.api_key = key;
    const current = ++requestId.current;
    const isCurrent = () => mounted.current && getToken() === token && requestId.current === current;
    writing.current = true;
    setStatus('saving');
    try {
      const settings = readSettings(await updateHomeworkAISettings(body));
      if (!isCurrent()) return;
      if (settings.provider !== body.provider || settings.model !== body.model
        || (settings.provider !== 'default' && !settings.has_api_key)) {
        throw new Error('Settings were not confirmed');
      }
      applySettings(settings);
      setMessage('Homework AI settings saved.');
    } catch (err) {
      if (!isCurrent()) return;
      const fields = Object.fromEntries(Object.entries(fieldErrors(err))
        .filter(([name]) => ['provider', 'model', 'api_key'].includes(name)));
      setErrors(fields);
      if (!Object.keys(fields).length) setError('Could not save homework AI settings. Try again.');
    } finally {
      writing.current = false;
      if (isCurrent()) setStatus('ready');
    }
  };

  const remove = async () => {
    if (writing.current || !mounted.current || getToken() !== token) return;
    setConfirmRemove(false);
    clearMessages();
    const current = ++requestId.current;
    const isCurrent = () => mounted.current && getToken() === token && requestId.current === current;
    writing.current = true;
    setStatus('removing');
    try {
      const settings = readSettings(await deleteHomeworkAISettings());
      if (!isCurrent()) return;
      if (settings.provider !== 'default') throw new Error('Removal was not confirmed');
      applySettings(settings);
      setMessage('Homework AI connection removed. Abby’s default planner will be used.');
    } catch {
      if (isCurrent()) setError('Could not remove the homework AI connection. Try again.');
    } finally {
      writing.current = false;
      if (isCurrent()) setStatus('ready');
    }
  };

  return (
    <ParchmentCard id="homework-ai" ref={sectionRef} className="scroll-mt-24">
      <SectionHeader index={3} title="Homework AI" kicker="your family’s planning provider" className="mb-3" />
      <p className="font-body text-body text-ink-secondary">
        Choose the AI provider and model used when your family plans homework. Abby’s default planner
        keeps the existing setup. A connected provider receives the homework title and description
        to create a plan.
      </p>
      <p className="font-body text-caption text-ink-secondary mt-2">
        Provider API billing is separate from a ChatGPT or Claude subscription. Your key is saved
        encrypted on the server and is never returned to the browser. Only parents can manage this
        family connection.
      </p>
      {status === 'loading' && <p role="status" aria-busy="true" className="font-body text-body text-ink-whisper mt-3">Loading homework AI settings…</p>}
      {loadError && <div className="mt-3 space-y-3"><ErrorAlert message={loadError} /><Button variant="secondary" onClick={load}>Retry homework AI settings</Button></div>}
      {saved && !loadError && status !== 'loading' && (
        <form noValidate onSubmit={save} className="mt-4 space-y-3" aria-busy={busy}>
          {error && <ErrorAlert message={error} />}
          {message && <p role="status" className="font-body text-body text-sheikah-teal-deep">{message}</p>}
          <SelectField label="AI provider" value={provider} error={errors.provider} disabled={busy}
            helpText={provider === 'default' && saved.provider !== 'default'
              ? 'Saving the default planner removes your family’s saved API key.' : undefined}
            onChange={(event) => changeProvider(event.target.value)}>
            {HOMEWORK_AI_PROVIDERS.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
          </SelectField>
          {provider !== 'default' && <>
            <SelectField label="Model" value={modelChoice} error={modelChoice === 'custom' ? undefined : errors.model}
              disabled={busy} helpText="Choose a model available to your provider account, or enter its API model ID."
              onChange={(event) => { setModelChoice(event.target.value); setCustomModel(''); clearMessages(); }}>
              {HOMEWORK_AI_MODELS[provider].map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
              <option value="custom">Custom model ID</option>
            </SelectField>
            {modelChoice === 'custom' && <TextField label="Custom model ID" value={customModel} error={errors.model}
              disabled={busy} autoComplete="off" spellCheck={false}
              onChange={(event) => { setCustomModel(event.target.value); clearMessages(); }} />}
            <TextField label="API key" type="password" value={apiKey} error={errors.api_key}
              disabled={busy} autoComplete="new-password" autoCapitalize="off" spellCheck={false}
              helpText={saved.provider === provider && saved.has_api_key
                ? 'A key is saved for this provider. Leave blank to keep it, or enter a replacement.'
                : 'Enter an API key for this provider to connect your family.'}
              onChange={(event) => { setApiKey(event.target.value); clearMessages(); }} />
          </>}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={busy || !dirty}>{status === 'saving' ? 'Saving…' : 'Save homework AI'}</Button>
            {saved.provider !== 'default' && <Button variant="danger" disabled={busy} onClick={() => setConfirmRemove(true)}>
              {status === 'removing' ? 'Removing…' : 'Remove connection'}
            </Button>}
          </div>
        </form>
      )}
      {confirmRemove && <ConfirmDialog title="Remove homework AI connection?"
        message="This deletes your family’s saved API key and switches future homework plans to Abby’s default planner. Existing plans stay available."
        confirmLabel="Remove connection" onConfirm={remove} onCancel={() => setConfirmRemove(false)} />}
    </ParchmentCard>
  );
}
