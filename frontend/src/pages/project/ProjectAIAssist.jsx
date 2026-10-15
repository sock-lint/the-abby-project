import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { draftProjectPlan, draftExistingProjectPlan, applyProjectPlan } from '../../api';
import { getToken } from '../../api/client';
import { fieldErrors } from '../../utils/api';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import { usePlanningAccount } from '../../components/project-plan/usePlanningAccount';
import { cleanProjectPlan, readProjectPlanResponse } from '../../components/project-plan/projectPlan';
import PlanDraftEditor from '../../components/project-plan/PlanDraftEditor';
import BottomSheet from '../../components/BottomSheet';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import { TextAreaField } from '../../components/form';

function errorMessage(err, fallback) {
  const message = err?.response?.detail || err?.response?.error;
  return typeof message === 'string' ? message : fallback;
}

export default function ProjectAIAssist(props) {
  const { user, accountKey } = usePlanningAccount();
  if (user?.role !== 'parent') return null;
  return <AssistForm key={`${accountKey}:${props.project?.id ?? 'new'}`} {...props} />;
}

function AssistForm({ project, source, plan, onChange, disabled = false, onBusyChange, onSourceErrors, onApplied, onRefresh }) {
  const navigate = useNavigate();
  const existing = Boolean(project);
  const [token] = useState(getToken);
  const [open, setOpen] = useState(false);
  const [localPlan, setLocalPlan] = useState(null);
  const [version, setVersion] = useState(null);
  const [guidance, setGuidance] = useState('');
  const [error, setError] = useState('');
  const [guidanceError, setGuidanceError] = useState('');
  const [status, setStatus] = useState('ready');
  const [conflict, setConflict] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const draft = existing ? localPlan : plan;
  const setDraft = existing ? setLocalPlan : onChange;
  const busy = status !== 'ready';
  const mounted = useRef(false);
  const writing = useRef(false);
  const requests = useRef(0);
  const currentInput = useRef(null);
  currentInput.current = JSON.stringify({ source, guidance });
  usePwaUpdateGuard(Boolean(draft) || busy || Boolean(guidance));

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; requests.current += 1; };
  }, []);

  const generate = async () => {
    if (writing.current || disabled || !mounted.current || getToken() !== token) return;
    setConfirmation(null);
    setError('');
    setGuidanceError('');
    const sourceErrors = {};
    if (!existing) {
      if (!source?.title?.trim()) sourceErrors.title = 'Enter a project title before drafting a plan.';
      if (source?.title?.length > 200) sourceErrors.title = 'Use at most 200 characters for the title.';
      if (source?.description?.length > 10000) sourceErrors.description = 'Use at most 10000 characters for the description.';
      if (!Number.isInteger(Number(source?.difficulty)) || Number(source?.difficulty) < 1 || Number(source?.difficulty) > 5) {
        sourceErrors.difficulty = 'Choose a difficulty from 1 to 5.';
      }
    }
    onSourceErrors?.(sourceErrors);
    if (Object.keys(sourceErrors).length) return;
    if (guidance.length > 2000) { setGuidanceError('Use at most 2000 characters for planning guidance.'); return; }
    const snapshot = currentInput.current;
    const request = ++requests.current;
    const isCurrent = () => mounted.current && getToken() === token && request === requests.current;
    const body = existing ? {} : { title: source.title, description: source.description, difficulty: Number(source.difficulty) };
    if (guidance.trim()) body.guidance = guidance.trim();
    writing.current = true;
    setStatus('generating');
    onBusyChange?.(true);
    try {
      const response = await (existing ? draftExistingProjectPlan(project.id, body) : draftProjectPlan(body));
      if (!isCurrent()) return;
      if (snapshot !== currentInput.current) {
        setError('Your project idea changed while the plan was being drafted. Draft again to use the latest details.');
        return;
      }
      const result = readProjectPlanResponse(response, existing);
      setDraft(result.plan);
      setVersion(result.plan_version);
      setConflict(false);
    } catch (err) {
      if (!isCurrent()) return;
      const fields = fieldErrors(err);
      setGuidanceError(fields.guidance || '');
      onSourceErrors?.(Object.fromEntries(Object.entries(fields).filter(([key]) => ['title', 'description', 'difficulty'].includes(key))));
      if (!fields.guidance && !fields.title && !fields.description && !fields.difficulty) {
        setError(errorMessage(err, err?.status ? 'Could not draft a plan. Try again, or check your Planning AI settings.' : err?.message || 'Could not draft a plan. Try again.'));
      }
    } finally {
      writing.current = false;
      if (isCurrent()) { setStatus('ready'); onBusyChange?.(false); }
    }
  };

  const apply = async () => {
    if (!existing || !draft || conflict || writing.current || disabled || !mounted.current || getToken() !== token) return;
    setError('');
    let reviewed;
    try { reviewed = cleanProjectPlan(draft); } catch (err) { setError(err.message); return; }
    const request = ++requests.current;
    const isCurrent = () => mounted.current && getToken() === token && request === requests.current;
    writing.current = true;
    setStatus('applying');
    try {
      const response = await applyProjectPlan(project.id, { plan: reviewed, plan_version: version });
      if (!isCurrent()) return;
      if (response?.applied !== true) throw new Error('The plan could not be confirmed. Refresh the project before trying again.');
      setLocalPlan(null);
      setVersion(null);
      setOpen(false);
      setGuidance('');
      onApplied?.();
    } catch (err) {
      if (!isCurrent()) return;
      if (err?.status === 409) {
        setConflict(true);
        setError('The project changed since this draft was generated. Your draft is kept. Generate a new draft to review the current project before adding it.');
        onRefresh?.();
      } else {
        setError(errorMessage(err, err?.status ? 'Could not add this plan. Your draft is kept so you can try again.' : err?.message || 'Could not add this plan. Try again.'));
      }
    } finally {
      writing.current = false;
      if (isCurrent()) setStatus('ready');
    }
  };

  const discard = () => {
    setDraft(null);
    setVersion(null);
    setError('');
    setConflict(false);
    setConfirmation(null);
  };
  const close = () => { discard(); setGuidance(''); setOpen(false); };
  const requestGenerate = () => draft ? setConfirmation('replace') : generate();

  const content = <div className="space-y-3">
    {!existing && <h2 className="font-display text-lg text-ink-primary">AI assist</h2>}
    <p className="text-body text-ink-secondary">
      {existing
        ? 'Draft additions using your project description, saved plan and optional guidance. Review every suggestion before adding it. Saved progress and payments stay as they are.'
        : 'Use your title, description and difficulty to draft milestones, steps and materials. Review and edit the suggestions before creating your project.'}
    </p>
    <p className="text-caption text-ink-secondary">Uses your family’s saved OpenAI or Claude connection. Private parent notes and payment details stay out of the AI request.</p>
    <Link to="/settings#homework-ai" className="inline-flex min-h-11 items-center text-body underline text-sheikah-teal-deep"
      onClick={(event) => { if (draft) { event.preventDefault(); setConfirmation('settings'); } }}>Planning AI settings</Link>
    <TextAreaField label="Planning guidance" value={guidance} rows={2} maxLength={2000} disabled={busy || disabled}
      error={guidanceError} helpText="Optional: describe available tools, time, experience or changes you want."
      onChange={(event) => { setGuidance(event.target.value); setGuidanceError(''); }} />
    {error && <ErrorAlert message={error} />}
    {status === 'generating' && <p role="status" aria-busy="true" className="text-body text-ink-secondary">Drafting your plan…</p>}
    <div className="flex flex-wrap gap-3">
      <Button variant="secondary" disabled={busy || disabled} onClick={requestGenerate} aria-busy={status === 'generating' || undefined}>
        {status === 'generating' ? 'Drafting…' : draft ? 'Regenerate plan' : 'Draft plan with AI'}
      </Button>
      {draft && <Button variant="ghost" disabled={busy || disabled} onClick={() => setConfirmation('discard')}>Discard plan draft</Button>}
    </div>
    {draft && <PlanDraftEditor plan={draft} onChange={setDraft} disabled={busy || disabled} />}
    {existing && draft && <Button disabled={busy || disabled || conflict || !Object.values(draft).some((items) => items.length)}
      aria-busy={status === 'applying' || undefined} onClick={apply}>{status === 'applying' ? 'Adding…' : 'Add to project'}</Button>}
  </div>;

  return <>
    {existing ? <>
      <Button variant="secondary" onClick={() => setOpen(true)}>AI assist</Button>
      {open && <BottomSheet title="AI assist" onClose={close} dirty={Boolean(draft || guidance)} disabled={busy}>{content}</BottomSheet>}
    </> : <section className="rounded-xl border border-ink-page-shadow p-3 space-y-3" aria-label="AI project planning">{content}</section>}
    {confirmation && <ConfirmDialog stacked={existing} title={confirmation === 'replace' ? 'Replace this plan draft?' : 'Discard this plan draft?'}
      message={confirmation === 'replace' ? 'This replaces your unsaved draft with newly generated suggestions. Your saved project stays as it is.' : 'Your unsaved plan draft will be removed. Your saved project stays as it is.'}
      confirmLabel={confirmation === 'replace' ? 'Generate new draft' : confirmation === 'settings' ? 'Open settings' : 'Discard draft'}
      onCancel={() => setConfirmation(null)} onConfirm={() => {
        if (confirmation === 'replace') void generate();
        else { const settings = confirmation === 'settings'; discard(); if (settings) navigate('/settings#homework-ai'); }
      }} />}
  </>;
}
