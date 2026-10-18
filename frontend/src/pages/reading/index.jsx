import { useEffect, useRef, useState } from 'react';
import { BookOpen, Check, Clock3, Headphones, Plus } from 'lucide-react';
import {
  listReadingBooks, listReadingSessions, getReadingSummary,
  deleteReadingBook, deleteReadingSession,
} from '../../api';
import { getToken } from '../../api/client';
import { useApi, friendlyErrorMessage } from '../../hooks/useApi';
import { usePulse } from '../../providers/pulseContext';
import useChildContext from '../../hooks/useChildContext';
import ChildContext from '../../components/family/ChildContext';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/Button';
import ConfirmDialog from '../../components/ConfirmDialog';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import SectionHeader from '../../components/SectionHeader';
import TomeShelf from '../../components/atlas/TomeShelf';
import { normalizeList } from '../../utils/api';
import { formatDate, formatDuration } from '../../utils/format';
import QuestFolio from '../quests/QuestFolio';
import BookForm from './BookForm';
import SessionForm from './SessionForm';
import ReadingAdventure from './ReadingAdventure';
import ReadingDiscovery from './ReadingDiscovery';
import { BookCover, BookLinks } from './DiscoveryBookCard';
import { BOOK_STATUSES, REACTIONS, labelFor } from './reading.constants';

// A complete shelf keeps every saved book available in the session chooser.
// Only a page number is followed; server URLs never choose an account or host.
async function loadShelf(params, signal, credential) {
  const books = [];
  const visited = new Set();
  let page;
  for (let index = 0; index < 100; index += 1) {
    if (getToken() !== credential || signal.aborted) throw new DOMException('Session changed', 'AbortError');
    const response = await listReadingBooks({ ...params, ...(page ? { page } : {}) }, { signal });
    if (getToken() !== credential || signal.aborted) throw new DOMException('Session changed', 'AbortError');
    books.push(...normalizeList(response));
    if (!response.next) return books;
    page = new URL(response.next, window.location.origin).searchParams.get('page');
    if (!page || visited.has(page)) throw new Error('Could not load the complete bookshelf. Try again.');
    visited.add(page);
  }
  throw new Error('This bookshelf is too large to load. Please ask a parent for help.');
}

export default function Reading() {
  const context = useChildContext();
  if (!context.user) return <Loader />;
  return <div className="space-y-5">
    {context.isParent && <ChildContext children={context.children} selectedChildId={context.targetUserId} onSelect={context.selectChild} />}
    {context.loading ? <Loader /> : context.error ? <ErrorAlert message={context.error} onRetry={context.reload} /> : !context.targetUserId ? <EmptyState>Add a child in Manage to start a family bookshelf.</EmptyState> : <ReadingWorkspace key={`${context.scope}:${context.targetUserId}`} context={context} credential={getToken()} />}
  </div>;
}

function ReadingWorkspace({ context, credential }) {
  const { pulse, refresh: refreshPulse } = usePulse();
  const params = context.isParent ? { user_id: context.targetUserId } : {};
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const current = () => mounted.current && getToken() === credential;
  const shelf = useApi((signal) => loadShelf(params, signal, credential));
  const guardedRead = async (read) => {
    const response = await read();
    if (getToken() !== credential) throw new DOMException('Session changed', 'AbortError');
    return response;
  };
  const history = useApi((signal) => guardedRead(() => listReadingSessions(params, { signal })));
  const summary = useApi((signal) => guardedRead(() => getReadingSummary(params, { signal })), [pulse]);
  const [discoveryRefresh, setDiscoveryRefresh] = useState(0);
  const [similarBook, setSimilarBook] = useState(null);
  const [filter, setFilter] = useState('reading');
  const [modal, setModal] = useState(null);
  const [receipt, setReceipt] = useState('');
  const [removal, setRemoval] = useState(null);
  const removalInFlight = useRef(false);
  const [removing, setRemoving] = useState(false);
  const [mutationError, setMutationError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState('');
  const books = (shelf.data ?? []).filter((book) => String(book.user) === String(context.targetUserId));
  const sessions = normalizeList(history.data).filter((session) => String(session.user) === String(context.targetUserId));
  const visibleBooks = books.filter((book) => book.status === filter);
  const stats = summary.data;
  const refresh = () => { void shelf.reload(); void history.reload(); void summary.reload(); setDiscoveryRefresh((value) => value + 1); };
  const savedBook = (book) => {
    if (!current()) return;
    shelf.setData((previous) => [book, ...(previous ?? []).filter((value) => value.id !== book.id)]);
    setFilter(book.status);
    setModal(null);
    setReceipt(`“${book.title}” saved to ${BOOK_STATUSES.find(([value]) => value === book.status)?.[1] ?? 'your shelf'}.`);
    refresh();
  };
  const savedSession = (session) => {
    if (!current()) return;
    history.setData((previous) => ({ ...previous, results: [session, ...normalizeList(previous).filter((value) => value.id !== session.id)] }));
    setModal(null);
    const reward = session.reading_reward;
    setReceipt(`Reading ${modal?.session ? 'changes ' : ''}saved for “${session.book_title}”. ${reward ? `Daily reading reward recorded: ${reward.xp_awarded} Reading Comprehension XP and ${reward.coins_awarded} Coins on ${formatDate(reward.day)}.` : 'You can find it in your reading history.'}`);
    refresh();
    // Re-read confirmed balances and notifications through the shared shell.
    // A saved/replayed receipt is never added to a local balance.
    void refreshPulse();
  };
  const remove = async () => {
    if (removalInFlight.current || !current()) return;
    removalInFlight.current = true;
    setRemoving(true);
    setMutationError('');
    try {
      if (removal.kind === 'book') await deleteReadingBook(removal.item.id);
      else await deleteReadingSession(removal.item.id);
      if (!current()) return;
      if (removal.kind === 'book') shelf.setData((previous) => previous.filter((book) => book.id !== removal.item.id));
      else history.setData((previous) => ({ ...previous, results: normalizeList(previous).filter((session) => session.id !== removal.item.id) }));
      setReceipt(removal.kind === 'book' ? 'Book removed from your shelf.' : 'Reading log removed.');
      setRemoval(null);
      refresh();
    } catch (error) {
      if (current()) {
        setMutationError(error.status === 409 && removal.kind === 'book' ? 'This book has reading history. Keep it on your shelf and choose Paused or Finished instead.' : friendlyErrorMessage(error));
        setRemoval(null);
      }
    } finally { removalInFlight.current = false; if (current()) setRemoving(false); }
  };
  const loadMore = async () => {
    if (loadingMore || !history.data?.next || !current()) return;
    setLoadingMore(true);
    setMoreError('');
    try {
      const page = new URL(history.data.next, window.location.origin).searchParams.get('page');
      if (!page) throw new Error('Could not load more reading history. Try again.');
      const response = await listReadingSessions({ ...params, page });
      if (current()) history.setData((previous) => ({ ...response, results: [...normalizeList(previous), ...normalizeList(response).filter((row) => !normalizeList(previous).some((saved) => saved.id === row.id))] }));
    } catch (error) { if (current()) setMoreError(friendlyErrorMessage(error)); }
    finally { if (current()) setLoadingMore(false); }
  };
  if (getToken() !== credential) return <Loader />;
  return <QuestFolio letter="R" title="Reading" kicker="One good book at a time" meta={stats ? `${stats.sessions_total} reading sessions` : 'Your books, your pace'} stats={stats ? [
    { value: stats.books_finished, label: 'finished' }, { value: stats.total_minutes, label: 'minutes' }, { value: stats.total_pages, label: 'pages' },
  ] : []}>
    <div className="space-y-3">
      <p className="text-body text-ink-secondary">Keep a little of every story. Save your books, track what you read or listened to, and find your next favorite.</p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setModal({ kind: 'session' })} disabled={!books.length || !stats?.today || shelf.loading}><BookOpen className="h-4 w-4" aria-hidden="true" /> Log reading</Button>
        <Button variant="secondary" onClick={() => setModal({ kind: 'book' })}><Plus className="h-4 w-4" aria-hidden="true" /> Add a book</Button>
      </div>
    </div>
    {receipt && <div role="status" className="flex items-start gap-2 rounded-xl border border-moss/30 bg-moss/10 p-3 text-body text-ink-primary"><Check className="h-5 w-5 shrink-0 text-moss" aria-hidden="true" /><p>{receipt}</p></div>}
    <ErrorAlert message={mutationError} />
    <ErrorAlert message={summary.error ? `Reading totals unavailable. ${summary.error}` : ''} onRetry={summary.reload} />
    <ReadingAdventure adventure={summary.error ? null : stats?.reading_adventure} />

    <section aria-label="Your bookshelf" className="space-y-3">
      <SectionHeader as="h3" title="Your bookshelf" index={0} count={shelf.data ? books.length : undefined} />
      <ErrorAlert message={shelf.error} onRetry={shelf.reload} />
      {shelf.loading ? <Loader /> : <>
        <TomeShelf ariaLabel="Bookshelf status" activeId={filter} onSelect={setFilter} items={BOOK_STATUSES.map(([id, name]) => ({ id, name, icon: id === 'finished' ? '✓' : id === 'want_to_read' ? '♡' : id === 'paused' ? 'Ⅱ' : '▤', chip: books.filter((book) => book.status === id).length, variant: 'vessel' }))} />
        {visibleBooks.length ? <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {visibleBooks.map((book) => <BookCard key={book.id} book={book} canLog={Boolean(stats?.today)} onLog={() => setModal({ kind: 'session', selectedBook: book })} onEdit={() => setModal({ kind: 'book', book })} onRemove={() => setRemoval({ kind: 'book', item: book })} onSimilar={() => setSimilarBook(book.catalog_entry)} />)}
        </div> : !shelf.error && <EmptyState icon={<BookOpen className="h-8 w-8" />} action={<Button variant="secondary" onClick={() => setModal({ kind: 'book' })}>Add a book</Button>}>
          <p className="font-bold text-ink-primary">{books.length ? `No books on your ${BOOK_STATUSES.find(([value]) => value === filter)?.[1].toLowerCase()} shelf yet.` : 'Your next story starts here.'}</p>
          <p className="mt-1 text-body">{books.length ? 'Change a book’s shelf with Edit book, or add another.' : 'Add a book you are reading, or save one you would like to try.'}</p>
        </EmptyState>}
      </>}
    </section>

    <ReadingDiscovery context={context} credential={credential} books={books} shelfReady={Boolean(shelf.data) && !shelf.error} refreshKey={discoveryRefresh} onChooseBook={(suggestion) => setModal({ kind: 'book', suggestion })} similarBook={similarBook} onSimilar={setSimilarBook} />

    <section aria-label="Reading history" className="space-y-3">
      <SectionHeader as="h3" title="Reading history" index={2} />
      <ErrorAlert message={history.error} onRetry={history.reload} />
      {history.loading ? <Loader /> : sessions.length ? <ul className="space-y-3">
        {sessions.map((session) => <li key={session.id}><SessionCard session={session} onEdit={() => setModal({ kind: 'session', session })} onRemove={() => setRemoval({ kind: 'session', item: session })} /></li>)}
      </ul> : !history.error && <p className="rounded-xl bg-ink-page-aged p-4 text-body text-ink-secondary">Nothing logged yet. A few pages, a chapter, or some audiobook time all count.</p>}
      <ErrorAlert message={moreError} onRetry={loadMore} />
      {history.data?.next && <Button variant="secondary" loading={loadingMore} onClick={loadMore}>Show earlier reading</Button>}
    </section>


    {modal?.kind === 'book' && <BookForm book={modal.book} suggestion={modal.suggestion} userId={context.isParent ? context.targetUserId : null} credential={credential} onClose={() => setModal(null)} onSaved={savedBook} />}
    {modal?.kind === 'session' && <SessionForm session={modal.session} selectedBook={modal.selectedBook} books={books} today={stats?.today} adventure={summary.error ? null : stats?.reading_adventure} userId={context.isParent ? context.targetUserId : null} credential={credential} onClose={() => setModal(null)} onSaved={savedSession} />}
    {removal && <ConfirmDialog title={removal.kind === 'book' ? 'Remove book?' : 'Delete reading log?'} message={removing ? 'Removing…' : removal.kind === 'book' ? `Remove “${removal.item.title}” from this bookshelf? Books with reading logs are kept so your history stays intact.` : `Delete this reading log for “${removal.item.book_title}”? This also removes its reading note and updates the totals. Credited reward minutes and earned rewards are kept.`} confirmLabel={removing ? 'Removing…' : 'Delete'} onCancel={() => { if (!removing) setRemoval(null); }} onConfirm={remove} />}
  </QuestFolio>;
}

function BookCard({ book, onLog, onEdit, onRemove, canLog, onSimilar }) {
  return <ParchmentCard as="article" aria-label={book.title} className="!p-4 space-y-3">
    <div className="flex gap-3 items-start">
      <BookCover book={book.catalog_entry ?? book} />
      <div className="min-w-0 space-y-1"><h4 className="text-lede font-bold text-ink-primary break-words">{book.title}</h4>{book.author && <p className="text-body text-ink-secondary break-words">{book.author}</p>}
        <div className="flex flex-wrap gap-1">{book.interests.map((tag) => <RuneBadge key={tag} tone="moss">{labelFor(tag)}</RuneBadge>)}</div>
      </div>
    </div>
    {book.catalog_entry?.series && <p className="text-caption text-moss-deep">Book {book.catalog_entry.series.position} in {book.catalog_entry.series.title}</p>}
    <BookLinks book={book.catalog_entry ?? book} />
    <div className="flex flex-wrap gap-2">
      {book.catalog_entry && <Button size="sm" variant="ghost" onClick={onSimilar}>More like this<span className="sr-only">: {book.title}</span></Button>}
      <Button size="sm" onClick={onLog} disabled={!canLog}>Log reading<span className="sr-only">: {book.title}</span></Button>
      <Button size="sm" variant="secondary" onClick={onEdit}>Edit book<span className="sr-only">: {book.title}</span></Button>
      <Button size="sm" variant="ghost" onClick={onRemove} aria-label={`Remove book: ${book.title}`}>Remove</Button>
    </div>
  </ParchmentCard>;
}

function SessionCard({ session, onEdit, onRemove }) {
  const reaction = REACTIONS.find(([value]) => value === session.reaction)?.[1];
  return <ParchmentCard as="article" aria-label={`Reading log: ${session.book_title}`} className="!p-4 space-y-3">
    <div className="flex items-start gap-3"><span className="rounded-xl bg-sheikah-teal/10 p-2 text-sheikah-teal-deep" aria-hidden="true">{session.format === 'audiobook' ? <Headphones className="h-5 w-5" /> : <BookOpen className="h-5 w-5" />}</span>
      <div className="min-w-0"><h4 className="font-bold text-ink-primary break-words">{session.book_title}</h4><p className="text-caption text-ink-secondary"><time dateTime={session.occurred_on}>{formatDate(session.occurred_on)}</time>{session.section ? ` · ${session.section}` : ''}</p></div>
    </div>
    <div className="flex flex-wrap items-center gap-3 text-caption text-ink-secondary">
      {session.duration_minutes > 0 && <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" aria-hidden="true" />{formatDuration(session.duration_minutes)}</span>}
      {session.pages_read > 0 && <span>{session.pages_read} pages</span>}
      <span>{session.format === 'audiobook' ? 'Audiobook' : session.format === 'ebook' ? 'Ebook' : 'Print book'}</span>
      {session.reaction && reaction && <RuneBadge tone="moss">{reaction}</RuneBadge>}
    </div>
    {session.reflection && <div className="rounded-xl bg-ink-page-rune-glow p-3"><p className="whitespace-pre-wrap break-words text-body text-ink-primary">{session.reflection}</p><p className="mt-2 text-tiny text-ink-secondary">Shared with parents</p></div>}
    {session.reading_reward && <p className="text-caption font-semibold text-moss-deep">Daily reading reward: {session.reading_reward.xp_awarded} Reading Comprehension XP · {session.reading_reward.coins_awarded} Coins · earned {formatDate(session.reading_reward.day)}</p>}
    <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={onEdit}>Edit log<span className="sr-only">: {session.book_title}</span></Button><Button size="sm" variant="ghost" onClick={onRemove}>Delete log<span className="sr-only">: {session.book_title}</span></Button></div>
  </ParchmentCard>;
}
