import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createContentDraft, getContentDraft, getContentWorkbench, previewContentDraft,
  publishContentDraft, simulateContentDraft, updateContentDraft,
} from '../../api';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import Button from '../../components/Button';
import CatalogSearch from '../../components/CatalogSearch';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import PageShell from '../../components/layout/PageShell';
import PageHeader from '../../components/layout/PageHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import { SelectField, TextField } from '../../components/form';
import ContentEntryEditor from './ContentEntryEditor';
import { editorChange, initialEditor, itemVersion } from './contentWorkbenchEditor';
import ContentDraftReview, { AuditFindings } from './ContentDraftReview';

export default function ContentWorkbench() {
  const { user } = useAuth();
  if (!user?.id) return <Loader />;
  if (user.role !== 'parent') return <PageShell><PageHeader title="RPG content" /><p>RPG content management is available to staff parents.</p></PageShell>;
  return <AccountWorkbench key={`${user.id}:${user.role}:${user.family?.id ?? ''}:${getToken()}`} />;
}

function AccountWorkbench() {
  const [metadata, setMetadata] = useState(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [readError, setReadError] = useState(null);
  const [error, setError] = useState(null);
  const [editorError, setEditorError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(null);
  const [draftName, setDraftName] = useState('');
  const [section, setSection] = useState('quests');
  const [search, setSearch] = useState('');
  const [editor, setEditor] = useState(null);
  const [original, setOriginal] = useState(null);
  const [source, setSource] = useState(null);
  const [preview, setPreview] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [config, setConfig] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [notice, setNotice] = useState(null);
  const active = useRef(false);
  const request = useRef(null);
  const token = getToken();
  const dirty = Boolean(editor && JSON.stringify(editor) !== original);
  usePwaUpdateGuard(dirty || busy);

  const isCurrent = () => active.current && token === getToken();
  const read = async (signal) => {
    setLoading(true); setReadError(null);
    try {
      const response = await getContentWorkbench({ signal });
      if (!isCurrent()) return;
      setMetadata(response); setConfig((previous) => previous ?? response.simulation?.defaults ?? null);
    } catch (failure) {
      if (!isCurrent() || failure.name === 'AbortError') return;
      if ([401, 403].includes(failure.status)) setDenied(true);
      else setReadError(failure.message);
    } finally { if (isCurrent()) setLoading(false); }
  };
  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    read(controller.signal);
    return () => { active.current = false; controller.abort(); request.current?.abort(); };
    // The account and credential key remounts this component on identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const invalidate = () => { setPreview(null); setSimulation(null); setError(null); setNotice(null); };
  const rememberDraft = (updated) => {
    setDraft(updated);
    setMetadata((previous) => ({ ...previous, drafts: [...previous.drafts.filter((entry) => entry.id !== updated.id), updated] }));
  };
  const closeEditor = () => { setEditor(null); setOriginal(null); setSource(null); setEditorError(null); };
  const guard = (action) => {
    if (dirty) setConfirmation({ title: 'Discard unsaved editor changes?', message: 'Your saved draft will stay available. The unsaved changes in this editor will be discarded.', confirmLabel: 'Discard changes', action });
    else action();
  };
  const run = async (action, onSuccess, editorAction = false) => {
    if (busy) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(null); setEditorError(null); setNotice(null);
    try {
      const response = await action({ signal: controller.signal });
      if (isCurrent()) onSuccess(response);
    } catch (failure) {
      if (!isCurrent() || failure.name === 'AbortError') return;
      if ([401, 403].includes(failure.status)) setDenied(true);
      else {
        const message = `${failure.message} Your inputs have been kept.${failure.status === 409 ? ' Reload the saved draft and review again to resolve the conflict.' : ''}`;
        if (editorAction) setEditorError(message); else setError(message);
        if (failure.status === 409) { setPreview(null); setSimulation(null); }
      }
    } finally { if (isCurrent()) setBusy(false); }
  };
  const create = (event) => {
    event.preventDefault();
    guard(() => run((options) => createContentDraft({ name: draftName }, options), (response) => {
      rememberDraft(response); closeEditor(); invalidate(); setDraftName(''); setNotice('Draft created. Choose a challenge or item, or add a new entry.');
    }));
  };
  const loadDraft = (id) => guard(() => {
    if (!id) { setDraft(null); closeEditor(); invalidate(); return; }
    run((options) => getContentDraft(id, options), (response) => { rememberDraft(response); closeEditor(); setPreview(response.preview); setSimulation(null); setNotice('Saved draft loaded.'); });
  });
  const choose = (row, kind = section) => guard(() => {
    const next = initialEditor(kind, row, row?._changeKey ?? row?.key ?? (row ? undefined : crypto.randomUUID()));
    setEditor(next); setOriginal(JSON.stringify(next)); setSource(row); setEditorError(null); setSection(kind);
  });
  const save = () => {
    if (!draft || draft.published_at || busy) return;
    let change;
    try { change = editorChange(editor); } catch (failure) { setEditorError(failure.message); return; }
    const changes = [...draft.changes.filter((entry) => entry.key !== change.key), change];
    run((options) => updateContentDraft(draft.id, { revision: draft.revision, changes }, options), (response) => {
      rememberDraft(response); setOriginal(JSON.stringify(editor)); invalidate(); setNotice('Changes saved to draft. Published content is unchanged.');
    }, true);
  };
  const previewDraft = () => run((options) => previewContentDraft(draft.id, { revision: draft.revision }, options), (response) => { rememberDraft(response); setPreview(response.preview); setSimulation(null); });
  const removeEntry = () => setConfirmation({
    title: 'Remove this entry from the draft?',
    message: 'The saved change and any unsaved edits to this entry will be removed from this draft. Published content stays available.',
    confirmLabel: 'Remove change',
    action: () => run((options) => updateContentDraft(draft.id, { revision: draft.revision, changes: draft.changes.filter((change) => change.key !== editor.key) }, options), (response) => {
      rememberDraft(response); closeEditor(); invalidate(); setNotice('Entry removed from the draft. Published content is unchanged.');
    }),
  });
  const simulate = () => run((options) => simulateContentDraft(draft.id, { revision: draft.revision, preview_id: preview.preview_id, config }, options), setSimulation);
  const publish = () => setConfirmation({
    title: 'Publish this reviewed draft?',
    message: `Publish ${draft.changes.length} saved ${draft.changes.length === 1 ? 'entry' : 'entries'} from “${draft.name}” to the shared catalog? This applies the exact preview and comparison you reviewed.`,
    confirmLabel: 'Publish now',
    action: () => run((options) => publishContentDraft(draft.id, { revision: draft.revision, preview_id: preview.preview_id, content_digest: preview.content_digest, confirmation: true }, options), (response) => {
      rememberDraft(response); setPreview(response.preview); closeEditor(); setNotice('Draft published. The shared catalog has been updated.');
      getContentWorkbench().then((data) => { if (isCurrent()) setMetadata(data); }).catch((failure) => {
        if (!isCurrent()) return;
        if ([401, 403].includes(failure.status)) setDenied(true);
        else setReadError(`Publication succeeded, but the catalog could not refresh. ${failure.message}`);
      });
    }),
  });

  const catalog = metadata ? {
    ...metadata.catalog,
    items: overlay(metadata.catalog.items, draft?.changes, 'items'),
    quests: overlay(metadata.catalog.quests, draft?.changes, 'quests'),
  } : null;
  const rows = catalog?.[section].filter((entry) => `${entry.name} ${entry.slug ?? ''} ${entry.description ?? ''}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  return <PageShell rhythm="loose">
    <PageHeader title="RPG content" kicker="Challenges, items and reward design" />
    <Link to="/manage?tab=Admin" className="inline-flex min-h-11 items-center text-sheikah-teal-deep underline font-semibold">Back to administration</Link>
    {denied ? <p role="status">RPG content management is available to staff parents.</p> : <>
      <p className="text-body text-ink-secondary">Manage challenges and items together. Save a private draft, inspect reward connections, then compare its progression forecast before publishing to the shared catalog.</p>
      <ErrorAlert message={readError} onRetry={() => read()} />
      {loading && <Loader />}
      {metadata && <>
        <ParchmentCard className="space-y-4">
          <SectionHeader title="Your content drafts" index={0}>Drafts are saved for your account and family. Saving a draft never changes published content.</SectionHeader>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-2"><SelectField label="Open draft" value={draft?.id ?? ''} disabled={busy} onChange={(event) => loadDraft(event.target.value)}><option value="">Browse published content</option>{metadata.drafts.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {entry.published_at ? 'published' : `revision ${entry.revision}`}</option>)}</SelectField>{draft && <Button variant="ghost" disabled={busy} onClick={() => loadDraft(draft.id)}>Reload saved draft</Button>}</div>
            <form aria-label="Create content draft" onSubmit={create} className="flex flex-wrap items-end gap-3"><TextField label="New draft name" value={draftName} maxLength="100" required disabled={busy} onChange={(event) => setDraftName(event.target.value)} className="flex-1 min-w-0" /><Button type="submit" disabled={busy || !draftName.trim()}>Create draft</Button></form>
          </div>
          {notice && <p role="status" className="text-body text-ink-secondary">{notice}</p>}
          {!draft && <ErrorAlert message={error} />}
        </ParchmentCard>
        <ParchmentCard className="space-y-4">
          <SectionHeader title="Challenges and items" index={1}>Browse published definitions and your saved draft changes in one place.</SectionHeader>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Content type"><Button variant="secondary" aria-pressed={section === 'quests'} disabled={busy} onClick={() => setSection('quests')}>Challenges</Button><Button variant="secondary" aria-pressed={section === 'items'} disabled={busy} onClick={() => setSection('items')}>Items</Button>{draft && !draft.published_at && <Button disabled={busy} onClick={() => choose(null)}>New {section === 'quests' ? 'challenge' : 'item'}</Button>}</div>
          <CatalogSearch ariaLabel="Search challenges and items" placeholder={`Search ${section === 'quests' ? 'challenges' : 'items'}…`} value={search} onChange={setSearch} />
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-4 items-start">
            <div className="max-h-[36rem] overflow-y-auto space-y-2" aria-label="Content catalog">{rows.length ? rows.map((row) => <Button key={row.id ?? row.key} variant="secondary" disabled={busy} aria-pressed={editor?.section === section && (row.id ? row.id === editor.object_id : row.key === editor.key)} onClick={() => choose(row)} className="w-full text-left flex flex-col items-start break-words"><span>{row.icon} {row.name}</span><span className="text-caption text-ink-secondary">{row._changeKey ? 'In this draft · ' : ''}{section === 'items' ? `${row.rarity} · ${row.item_type.replaceAll('_', ' ')}` : `${row.coin_reward} coins · ${row.xp_reward} XP`}</span></Button>) : <p role="status">No {section === 'quests' ? 'challenges' : 'items'} match this search.</p>}</div>
            <div className="min-w-0 space-y-4">{editor ? <>
              <ContentEntryEditor key={`${editor.section}:${editor.key}`} editor={editor} onChange={(next) => { setEditor(next); setEditorError(null); invalidate(); }} catalog={catalog} rules={metadata.rules} busy={busy} canSave={Boolean(draft && !draft.published_at)} source={source} error={editorError} onSave={save} onVersion={source?.id && editor.section === 'items' && !['egg', 'potion'].includes(source.item_type) ? () => choose(itemVersion(catalog.items.find((item) => item.id === source.id) ?? source, catalog.items), 'items') : null} onRemove={draft?.changes.some((change) => change.key === editor.key) ? removeEntry : null} onDiscard={() => guard(closeEditor)} />
              {editor.section === 'items' && source && <ItemUses item={source} changes={draft?.changes ?? []} onQuest={(id) => { const quest = catalog.quests.find((entry) => entry.id === id); if (quest) choose(quest, 'quests'); }} />}
            </> : <p className="text-body text-ink-secondary">Choose a challenge or item to inspect its details.{!draft ? ' Create or open a draft to make changes.' : ''}</p>}</div>
          </div>
        </ParchmentCard>
        {draft ? <ContentDraftReview draft={draft} preview={preview} simulation={simulation} metadata={metadata.simulation} config={config} onConfig={setConfig} onPreview={previewDraft} onSimulate={simulate} onPublish={publish} busy={busy} dirty={dirty} error={error} /> : metadata.audits && <ParchmentCard><AuditFindings audit={metadata.audits} title="Published reward audit" /></ParchmentCard>}
      </>}
    </>}
    {confirmation && <ConfirmDialog title={confirmation.title} message={confirmation.message} confirmLabel={confirmation.confirmLabel} onCancel={() => setConfirmation(null)} onConfirm={() => { const action = confirmation.action; setConfirmation(null); action(); }} />}
  </PageShell>;
}

function overlay(rows, changes = [], section) {
  const selected = (changes ?? []).filter((change) => change.section === section);
  return [...rows.map((row) => {
    const change = selected.find((entry) => entry.object_id === row.id);
    return change ? { ...row, ...change.values, values: { ...row.values, ...change.values }, _changeKey: change.key } : row;
  }), ...selected.filter((change) => !change.object_id).map((change) => ({ ...change.values, values: change.values, id: null, key: change.key, _changeKey: change.key, editable: true }))];
}

function ItemUses({ item, changes, onQuest }) {
  const uses = item.used_by ?? {};
  const draftUses = changes.filter((change) => change.section === 'quests' && change.values.reward_items?.some((reward) => item.id ? reward.item_id === item.id : reward.item_key === item.key));
  return <section aria-label="Item connections" className="space-y-3 rounded-lg bg-ink-page-aged p-3">
    <h3 className="font-semibold text-ink-primary">Availability and connections</h3>
    <p className="text-body text-ink-secondary">{item.runtime_available === false ? `Unavailable for new acquisition: ${item.unavailable_reason || 'No supported runtime offer.'}` : item.id ? 'Available for new acquisition under the current catalog rules.' : 'Draft availability will be checked in the preview.'}</p>
    <h4 className="font-semibold text-ink-primary">Published uses</h4>
    <ul className="space-y-2 text-body text-ink-secondary">{(uses.quests ?? []).map((quest) => <li key={quest.id}><Button variant="ghost" onClick={() => onQuest(quest.id)}>{quest.name} · {quest.quantity} awarded</Button></li>)}{(uses.drops ?? []).map((drop) => <li key={drop.id}>Drop: {drop.trigger_type.replaceAll('_', ' ')} · weight {drop.weight} · minimum level {drop.min_level}</li>)}{(uses.shop_offers ?? []).map((offer) => <li key={offer.id}>Shop: {offer.name} · {offer.cost_coins} coins · {offer.is_active ? 'active' : 'inactive'}</li>)}</ul>
    {![...(uses.quests ?? []), ...(uses.drops ?? []), ...(uses.shop_offers ?? [])].length && <p className="text-body text-ink-secondary">No published challenge, drop or visible shop offer references this item.</p>}
    {draftUses.length > 0 && <p className="text-body text-ink-secondary">Saved draft challenges using this item: {draftUses.map((change) => change.values.name || `challenge ${change.object_id}`).join(', ')}.</p>}
  </section>;
}
