import { useState } from 'react';
import { BookOpen, ExternalLink } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import { labelFor } from './reading.constants';

export function BookCover({ book }) {
  const [failedUrl, setFailedUrl] = useState(null);
  const url = /^https:\/\/covers\.openlibrary\.org\//.test(book?.cover_url ?? '') ? book.cover_url : null;
  return <div className="flex h-28 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-moss/20 bg-moss/10 text-moss-deep">
    {url && failedUrl !== url ? <img src={url} alt={`Cover of ${book.title}`} loading="lazy" referrerPolicy="no-referrer" className="h-full w-full object-contain" onError={() => setFailedUrl(url)} /> : <><BookOpen className="h-8 w-8" aria-hidden="true" /><span className="sr-only">Cover unavailable for {book?.title ?? 'this book'}</span></>}
  </div>;
}

function libraryUrl(book) {
  return `https://search.worldcat.org/search?q=${encodeURIComponent(`${book.title} ${book.author ?? ''}`.trim())}`;
}

export function BookLinks({ book }) {
  return <div className="flex flex-wrap gap-x-4 gap-y-1">
    {book.source_url && <a href={book.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-caption text-sheikah-teal-deep underline">About this book <ExternalLink className="h-3 w-3" aria-hidden="true" /><span className="sr-only">: {book.title} (opens a new tab)</span></a>}
    <a href={libraryUrl(book)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-caption text-sheikah-teal-deep underline">Find at a library <ExternalLink className="h-3 w-3" aria-hidden="true" /><span className="sr-only">: {book.title} (opens a new tab)</span></a>
  </div>;
}

export default function DiscoveryBookCard({ book, children, label }) {
  return <ParchmentCard as="article" aria-label={label ?? `Suggested book: ${book.title}`} className="space-y-3 !p-4">
    {book.reason_kind === 'series' && <p className="text-caption font-bold text-moss-deep">Continue a series</p>}
    <div className="flex items-start gap-3">
      <BookCover book={book} />
      <div className="min-w-0 space-y-1">
        <h4 className="text-lede font-bold text-ink-primary break-words">{book.title}</h4>
        <p className="text-body text-ink-secondary break-words">{book.author}</p>
        {book.age_min != null && <p className="text-caption text-ink-secondary">{book.age_max == null ? `Ages ${book.age_min}+` : `Ages ${book.age_min}–${book.age_max}`}</p>}
        {book.page_count != null && <p className="text-caption text-ink-secondary">{book.page_count} pages</p>}
        {book.series && <p className="text-caption font-semibold text-moss-deep">Book {book.series.position} in {book.series.title}</p>}
      </div>
    </div>
    <div className="flex flex-wrap gap-1">{(book.formats ?? []).map((format) => <RuneBadge key={format} tone="moss">{labelFor(format)}</RuneBadge>)}{(book.styles ?? []).map((style) => <RuneBadge key={style}>{labelFor(style)}</RuneBadge>)}</div>
    <p className="text-body text-ink-secondary">{book.description}</p>
    {book.reason && <p className="text-caption text-moss-deep font-semibold">{book.reason}</p>}
    <BookLinks book={book} />
    {children}
  </ParchmentCard>;
}
