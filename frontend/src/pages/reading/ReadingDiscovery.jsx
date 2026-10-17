import { useEffect, useRef, useState } from 'react';
import { getReadingRecommendations, saveReadingDiscoveryFeedback, listReadingFamilySuggestions, updateReadingFamilySuggestion } from '../../api';
import { getToken } from '../../api/client';
import { useApi, friendlyErrorMessage } from '../../hooks/useApi';
import Button from '../../components/Button';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import SectionHeader from '../../components/SectionHeader';
import { SelectField, TextField } from '../../components/form';
import { normalizeList } from '../../utils/api';
import DiscoveryBookCard from './DiscoveryBookCard';
import FamilySuggestionForm from './FamilySuggestionForm';
import { READING_INTERESTS, labelFor } from './reading.constants';

const FILTERS = [
  ['mood', 'What sounds good today?', ['funny', 'cozy', 'suspenseful', 'exciting', 'thoughtful']],
  ['style', 'Reading style', ['illustrated', 'graphic_novel', 'short_chapters', 'verse']],
  ['book_format', 'Book format', ['print', 'ebook', 'audiobook']],
  ['length', 'Book length', [['short', 'Short · up to 200 pages'], ['medium', 'Medium · 201–349 pages'], ['long', 'Long · 350+ pages']]],
  ['theme', 'Explore a theme', ['dragons', 'space', 'inventors', 'nature', 'animals', 'friendship', 'mythology', 'magic', 'puzzles', 'history', 'sports', 'music', 'family', 'identity']],
];
const onShelf = (book, books) => books.some((saved) => saved.title.toLowerCase().trim() === book.title.toLowerCase().trim() && saved.author.toLowerCase().trim() === book.author.toLowerCase().trim());

export default function ReadingDiscovery({ context, credential, books, shelfReady, refreshKey, onChooseBook, similarBook, onSimilar }) {
  const params = context.isParent ? { user_id: context.targetUserId } : {};
  const mounted = useRef(false);
  const inFlight = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const current = () => mounted.current && getToken() === credential;
  const guardedRead = async (read) => {
    const result = await read();
    if (!current()) throw new DOMException('Session changed', 'AbortError');
    return result;
  };
  const [filters, setFilters] = useState({});
  const [search, setSearch] = useState('');
  const [rotation, setRotation] = useState(0);
  const queryKey = JSON.stringify({ ...filters, similar_to: similarBook?.id, rotation });
  const recommendations = useApi((signal) => guardedRead(() => getReadingRecommendations({ ...params, ...JSON.parse(queryKey) }, { signal })), [queryKey, refreshKey]);
  const family = useApi((signal) => guardedRead(() => listReadingFamilySuggestions(params, { signal })), [refreshKey]);
  const [composer, setComposer] = useState(null);
  const [message, setMessage] = useState('');
  const [mutationError, setMutationError] = useState('');
  const [pendingAction, setPendingAction] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState([]);
  const [undo, setUndo] = useState(null);
  const [familyPageBusy, setFamilyPageBusy] = useState(false);
  const [familyPageError, setFamilyPageError] = useState('');
  const changeFilter = (key, value) => { setFilters((previous) => ({ ...previous, [key]: value })); setRotation(0); };
  const runAction = async (action) => {
    if (inFlight.current || !current()) return;
    inFlight.current = true;
    setBusy(true);
    setMutationError('');
    try {
      if (action.kind === 'dismiss') await updateReadingFamilySuggestion(action.id, { status: 'dismissed' });
      else await saveReadingDiscoveryFeedback({ ...params, catalog_id: action.book.id, choice: action.choice });
      if (!current()) return;
      setPendingAction(null);
      if (action.kind === 'dismiss') {
        family.setData((previous) => ({ ...previous, results: normalizeList(previous).filter((suggestion) => suggestion.id !== action.id) }));
        setMessage('Family suggestion dismissed.');
      } else if (action.choice) {
        setHidden((previous) => [...new Set([...previous, action.book.id])]);
        setUndo(action);
        setMessage(action.choice === 'already_read' ? `“${action.book.title}” hidden as already read. Your reading log is unchanged.` : `“${action.book.title}” hidden from your picks.`);
      } else {
        setHidden((previous) => previous.filter((id) => id !== action.book.id));
        setUndo(null);
        setMessage(`“${action.book.title}” can appear in your picks again.`);
        void recommendations.reload();
      }
    } catch (error) {
      if (!current()) return;
      const uncertain = !(error.status >= 400 && error.status < 500);
      setPendingAction(uncertain ? action : null);
      setMutationError(`${friendlyErrorMessage(error)}${uncertain ? ' Retry to confirm this change.' : ''}`);
    } finally {
      inFlight.current = false;
      if (current()) setBusy(false);
    }
  };
  const loadFamilyPage = async () => {
    if (familyPageBusy || !family.data?.next || !current()) return;
    setFamilyPageBusy(true);
    setFamilyPageError('');
    try {
      const page = new URL(family.data.next, window.location.origin).searchParams.get('page');
      if (!page) throw new Error('Could not load more family suggestions. Try again.');
      const response = await listReadingFamilySuggestions({ ...params, page });
      if (current()) family.setData((previous) => ({ ...response, results: [...normalizeList(previous), ...normalizeList(response).filter((row) => !normalizeList(previous).some((saved) => saved.id === row.id))] }));
    } catch (error) { if (current()) setFamilyPageError(friendlyErrorMessage(error)); }
    finally { if (current()) setFamilyPageBusy(false); }
  };
  const suggestions = normalizeList(recommendations.data).filter((book) => !hidden.includes(book.id));
  const familySuggestions = normalizeList(family.data).filter((suggestion) => String(suggestion.user) === String(context.targetUserId) && suggestion.status === 'pending');
  const disabled = busy || Boolean(pendingAction);
  return <section aria-label="Find your next read" className="space-y-3">
    <SectionHeader as="h3" title="Find your next read" index={1}><p>New worlds, familiar favorites, and a few happy surprises.</p></SectionHeader>
    <div className="rounded-xl border border-moss/20 bg-moss/5 p-3 space-y-3">
      <SelectField label="Explore a topic" value={filters.interest ?? ''} onChange={(event) => changeFilter('interest', event.target.value)}>
        <option value="">Picked for this reader</option>
        {READING_INTERESTS.map((value) => <option key={value} value={value}>{labelFor(value)}</option>)}
      </SelectField>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{FILTERS.slice(0, 1).map(([key, label, options]) => <SelectField key={key} label={label} value={filters[key] ?? ''} onChange={(event) => changeFilter(key, event.target.value)}><option value="">Any mood</option>{options.map((value) => <option key={value} value={value}>{labelFor(value)}</option>)}</SelectField>)}
        <form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); changeFilter('q', search.trim()); }}><TextField label="Search books" value={search} onChange={(event) => setSearch(event.target.value)} maxLength={160} className="min-w-0 flex-1" /><Button size="sm" type="submit" variant="secondary">Search</Button></form>
      </div>
      <details><summary className="min-h-11 cursor-pointer py-3 text-body font-bold text-ink-primary">More ways to choose</summary><div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{FILTERS.slice(1).map(([key, label, options]) => <SelectField key={key} label={label} value={filters[key] ?? ''} onChange={(event) => changeFilter(key, event.target.value)}><option value="">Any {key === 'book_format' ? 'format' : key}</option>{options.map((option) => { const [value, text] = Array.isArray(option) ? option : [option, labelFor(option)]; return <option key={value} value={value}>{text}</option>; })}</SelectField>)}</div></details>
      {similarBook && <p className="text-body text-ink-primary">More like <strong>{similarBook.title}</strong> <Button size="sm" variant="ghost" onClick={() => onSimilar(null)}>Clear similar book</Button></p>}
      <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" loading={recommendations.refreshing} disabled={recommendations.data?.has_more === false} onClick={() => setRotation((previous) => (previous + 1) % 1001)}><span>Show different books</span></Button><Button variant="ghost" size="sm" onClick={() => { setFilters({}); setSearch(''); setRotation(0); onSimilar(null); }}>Reset filters</Button></div>
    </div>
    <p className="text-caption text-ink-secondary">Suggestions use book topics and the reader’s age when available. Reading notes stay in Abby and are never sent to a recommendation service. Library links search a catalog; check local availability there.</p>
    {message && <div role="status" className="rounded-xl bg-moss/10 p-3 text-body text-ink-primary">{message}{undo && <Button size="sm" variant="ghost" disabled={disabled} onClick={() => void runAction({ ...undo, choice: '' })}>Undo</Button>}</div>}
    <ErrorAlert message={mutationError} onRetry={pendingAction ? () => void runAction(pendingAction) : undefined} />
    <ErrorAlert message={recommendations.error} onRetry={recommendations.reload} />
    {recommendations.loading ? <Loader /> : <>
      {recommendations.data?.basis && <p className="text-body text-ink-secondary">{recommendations.data.basis}</p>}
      {recommendations.data?.has_more === false && suggestions.length > 0 && <p className="text-caption text-ink-secondary">All matching books are shown. Try a different filter to explore more.</p>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">{suggestions.map((book) => {
        const saved = onShelf(book, books);
        return <DiscoveryBookCard key={book.id} book={book}>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={saved || !shelfReady} onClick={() => onChooseBook(book)}>{saved ? 'On your shelf' : 'Save to want to read'}</Button>
            {context.isParent && <Button size="sm" variant="secondary" onClick={() => setComposer(book)}>Send a suggestion<span className="sr-only">: {book.title}</span></Button>}
            <Button size="sm" variant="ghost" onClick={() => { onSimilar(book); setRotation(0); }}>More like this<span className="sr-only">: {book.title}</span></Button>
          </div>
          <div className="flex flex-wrap gap-2"><Button size="sm" variant="ghost" disabled={disabled} onClick={() => void runAction({ kind: 'feedback', book, choice: 'not_interested' })}>Not interested<span className="sr-only">: {book.title}</span></Button><Button size="sm" variant="ghost" disabled={disabled} onClick={() => void runAction({ kind: 'feedback', book, choice: 'already_read' })}>Already read<span className="sr-only">: {book.title}</span></Button></div>
        </DiscoveryBookCard>;
      })}</div>
      {!suggestions.length && !recommendations.error && <p className="text-body text-ink-secondary">No matching books right now. Try another topic or reset the filters.</p>}
    </>}
    <section aria-label="Family book suggestions" className="space-y-3">
      <h4 className="text-lede font-bold text-ink-primary">{context.isParent ? 'Family book suggestions' : 'Suggestions from your family'}</h4>
      <ErrorAlert message={family.error} onRetry={family.reload} />
      {family.loading ? <Loader /> : <>
        {!familySuggestions.length && !family.error && <p className="text-body text-ink-secondary">{context.isParent ? 'Send a book with a personal note. It stays a suggestion until your child chooses to save it.' : 'Books your parents suggest will appear here. You choose which ones to save.'}</p>}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">{familySuggestions.map((suggestion) => {
          const book = suggestion.catalog_entry;
          if (!book) return null;
          const saved = suggestion.on_shelf || onShelf(book, books);
          return <DiscoveryBookCard key={suggestion.id} book={book} label={`Family suggestion: ${book.title}`}>
            <p className="text-caption font-bold text-moss-deep">Suggested by {suggestion.suggested_by.display_name}</p>
            {suggestion.message && <p className="whitespace-pre-wrap break-words rounded-xl bg-moss/10 p-3 text-body text-ink-primary">{suggestion.message}</p>}
            {context.isParent && saved && <p className="text-caption font-bold text-moss-deep">Saved to their shelf</p>}
            <div className="flex flex-wrap gap-2">{!context.isParent && <Button size="sm" variant="secondary" disabled={saved || !shelfReady} onClick={() => onChooseBook(book)}>{saved ? 'On your shelf' : 'Save to want to read'}</Button>}<Button size="sm" variant="ghost" disabled={disabled} onClick={() => void runAction({ kind: 'dismiss', id: suggestion.id })}>Dismiss suggestion<span className="sr-only">: {book.title}</span></Button></div>
          </DiscoveryBookCard>;
        })}</div>
        <ErrorAlert message={familyPageError} onRetry={loadFamilyPage} />
        {family.data?.next && <Button size="sm" variant="secondary" loading={familyPageBusy} onClick={loadFamilyPage}>Show earlier suggestions</Button>}
      </>}
    </section>
    {composer && <FamilySuggestionForm book={composer} userId={context.targetUserId} credential={credential} onClose={() => setComposer(null)} onSaved={() => { if (!current()) return; setComposer(null); setMessage('Suggestion sent. Your child can choose whether to save it.'); void family.reload(); }} />}
  </section>;
}
