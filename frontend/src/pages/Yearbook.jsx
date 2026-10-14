import { useEffect, useMemo, useState } from 'react'

import Button from '../components/Button'
import EmptyState from '../components/EmptyState'
import ErrorAlert from '../components/ErrorAlert'
import Loader from '../components/Loader'
import ChildContext from '../components/family/ChildContext'
import useChildContext from '../hooks/useChildContext'
import { getToken } from '../api/client'
import TomeShelf from '../components/atlas/TomeShelf'
import {
  chapterMark,
  PROGRESS_TIER,
} from '../components/atlas/mastery.constants'
import { useRole } from '../hooks/useRole'
import useChronicleRevision from '../hooks/useChronicleRevision'
import { getChronicleSummary } from '../api'
import ChapterCard from './yearbook/ChapterCard'
import ManualEntryFormModal from './yearbook/ManualEntryFormModal'

const ACTIVE_CHAPTER_KEY_PREFIX = 'atlas:yearbook:active-chapter:'

export default function Yearbook() {
  const { user, isParent } = useRole()
  if (!user?.id) return <Loader />

  // Auth can change without this page unmounting. Keep the child list and
  // selection inside an account-scoped tree so neither survives that change.
  return <AccountYearbook key={`${user.id}:${user.role}:${user.family?.id ?? ''}:${getToken()}`} isParent={isParent} />
}

function AccountYearbook({ isParent }) {
  const { children, targetUserId, selectChild, loading, error, reload } = useChildContext()
  const revision = useChronicleRevision(targetUserId)

  if (isParent && loading) return <Loader />
  if (isParent && error) {
    return <YearbookLoadError error={error} onRetry={reload} />
  }
  if (isParent && children.length === 0) {
    return (
      <EmptyState>
        <p className="font-semibold mb-1">No children yet</p>
        <p>Create a child account on the Manage page to start their timeline.</p>
      </EmptyState>
    )
  }

  // A signed-in child can read saved memories without a birthday on file.
  return (
    <YearbookHistory
      key={`${targetUserId}:${revision}`}
      targetUserId={targetUserId}
      isParent={isParent}
      childOptions={children}
      onSelectChild={selectChild}
    />
  )
}

function YearbookLoadError({ error, onRetry }) {
  return (
    <div className="space-y-3 max-w-xl mx-auto">
      <ErrorAlert message={error?.message || (typeof error === 'string' ? error : 'Could not load the timeline.')} />
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}

function YearbookHistory({ targetUserId, isParent, childOptions, onSelectChild }) {
  // Remounting this tree on a target change immediately clears history,
  // entry dialogs/replies, and the add-memory draft together.
  const [state, setState] = useState({ loading: true, chapters: [], error: null })
  const [showAdd, setShowAdd] = useState(false)
  const [summaryRequest, setSummaryRequest] = useState(0)
  // User-clicked override per (target child). Derived effective active id
  // below uses this when valid and falls back when the chapter list shifts
  // — avoids a setState-in-effect for the "data changed" reconciliation.
  const [activeChapterOverride, setActiveChapterOverride] = useState({})

  // Initial loads, retries and post-save refreshes share the same cleanup
  // guard. A late response cannot replace another child/account's archive.
  const fetchSummary = () => setSummaryRequest((n) => n + 1)

  useEffect(() => {
    let cancelled = false
    getChronicleSummary(isParent ? targetUserId : undefined)
      .then((res) => {
        if (cancelled) return
        const chapters = (res?.chapters ?? []).map((chapter) => ({
          ...chapter,
          entries: (chapter.entries ?? []).filter((entry) =>
            entry.user === targetUserId && (!isParent || !['journal', 'grade'].includes(entry.kind) || entry.is_private === false)),
        }))
        setState({ loading: false, chapters, error: null })
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, chapters: [], error: err })
      })
    return () => {
      cancelled = true
    }
  }, [targetUserId, isParent, summaryRequest])

  // Keep chapter chips in chronological order, oldest to newest.
  const view = state

  const sortedChapters = useMemo(
    () => [...(view.chapters || [])].sort((a, b) => a.chapter_year - b.chapter_year),
    [view.chapters],
  )

  // Effective active chapter id — derived during render, per child.
  // Priority: (1) in-memory override for this child, (2) localStorage for
  // this child, (3) the chapter marked `is_current` by the backend,
  // (4) the latest chapter in the sorted list.
  const activeChapterId = useMemo(() => {
    if (!sortedChapters.length || !targetUserId) return null
    const override = activeChapterOverride[targetUserId]
    if (override && sortedChapters.some((c) => String(c.chapter_year) === override)) {
      return override
    }
    let stored = null
    try {
      stored = window.localStorage?.getItem(
        `${ACTIVE_CHAPTER_KEY_PREFIX}${targetUserId}`,
      )
    } catch {
      stored = null
    }
    if (stored && sortedChapters.some((c) => String(c.chapter_year) === stored)) {
      return stored
    }
    const current = sortedChapters.find((c) => c.is_current)
    return current
      ? String(current.chapter_year)
      : String(sortedChapters[sortedChapters.length - 1].chapter_year)
  }, [sortedChapters, targetUserId, activeChapterOverride])

  const setActiveChapterId = (id) => {
    if (!targetUserId) return
    setActiveChapterOverride((prev) => ({ ...prev, [targetUserId]: id }))
    try {
      window.localStorage?.setItem(`${ACTIVE_CHAPTER_KEY_PREFIX}${targetUserId}`, id)
    } catch {
      // ignore quota / disabled storage
    }
  }

  const shelfItems = sortedChapters.map((chapter, idx) => ({
    id: String(chapter.chapter_year),
    name: chapter.label || `Year ${chapter.chapter_year}`,
    icon: chapterMark(idx),
    chip: String(chapter.chapter_year),
    // Calendar chapters use compact chips without completion progress.
    variant: 'vessel',
    progressPct: null,
    tier: chapter.is_current ? PROGRESS_TIER.rising : PROGRESS_TIER.nascent,
    ariaLabel: `${chapter.label || `Year ${chapter.chapter_year}`}, ${chapter.chapter_year}`,
  }))

  const activeChapter =
    sortedChapters.find((c) => String(c.chapter_year) === activeChapterId)
    || sortedChapters[sortedChapters.length - 1]

  return (
    <div className="space-y-4">
      {/* Below md the Chronicle hub's tab strip already names this page —
          the stacked h1 + explainer ate ~100px above the fold on phones.
          Same treatment as the Skills tab (pages/Achievements.jsx). */}
      <header className="sr-only md:not-sr-only text-center max-w-xl mx-auto">
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Timeline
        </h1>
        <p className="font-script text-body text-ink-whisper mt-1">
          Browse memories, milestones, birthdays, and graduations by year.
        </p>
      </header>
      {isParent && (
        <ChildContext children={childOptions} selectedChildId={targetUserId} onSelect={onSelectChild}
          actions={<Button variant="secondary" onClick={() => setShowAdd(true)} disabled={!targetUserId}>Add memory</Button>} />
      )}
      {view.loading ? <Loader /> : view.error ? (
        <YearbookLoadError error={view.error} onRetry={fetchSummary} />
      ) : (
        <>
          {shelfItems.length > 0 && (
            <TomeShelf
              items={shelfItems}
              activeId={activeChapterId}
              onSelect={setActiveChapterId}
              ariaLabel="Timeline years"
            />
          )}
          {activeChapter && (
            <ChapterCard key={activeChapter.chapter_year} chapter={activeChapter} />
          )}
        </>
      )}
      {showAdd && targetUserId && (
        <ManualEntryFormModal
          userId={targetUserId}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false)
            fetchSummary()
          }}
        />
      )}
    </div>
  )
}
