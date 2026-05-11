import { useEffect, useMemo, useState } from 'react'

import Button from '../components/Button'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { SelectField } from '../components/form'
import TomeShelf from '../components/atlas/TomeShelf'
import {
  chapterMark,
  PROGRESS_TIER,
} from '../components/atlas/mastery.constants'
import { useRole } from '../hooks/useRole'
import { getChildren, getChronicleSummary } from '../api'
import { normalizeList } from '../utils/api'
import ChapterCard from './yearbook/ChapterCard'
import ManualEntryFormModal from './yearbook/ManualEntryFormModal'

const ACTIVE_CHAPTER_KEY_PREFIX = 'atlas:yearbook:active-chapter:'

export default function Yearbook() {
  const { user, isParent } = useRole()
  const [state, setState] = useState({ loading: true, chapters: [], error: null })
  const [showAdd, setShowAdd] = useState(false)
  const [children, setChildren] = useState([])
  const [selectedChildId, setSelectedChildId] = useState(null)
  // User-clicked override per (target child). Derived effective active id
  // below uses this when valid and falls back when the chapter list shifts
  // — avoids a setState-in-effect for the "data changed" reconciliation.
  const [activeChapterOverride, setActiveChapterOverride] = useState({})

  // The chronicle summary + the "Add memory" POST both need a target child.
  // Children view their own yearbook; parents pick from their kid list.
  const targetUserId = isParent ? selectedChildId : user?.id

  // Parent path: fetch kid list + default-select the first.
  useEffect(() => {
    if (!isParent) return undefined
    let cancelled = false
    getChildren()
      .then((res) => {
        if (cancelled) return
        const list = normalizeList(res)
        setChildren(list)
        if (list.length > 0) {
          setSelectedChildId((prev) => prev ?? list[0].id)
        } else {
          setState({ loading: false, chapters: [], error: null })
        }
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, chapters: [], error: err })
      })
    return () => {
      cancelled = true
    }
  }, [isParent])

  const fetchSummary = () => {
    if (isParent && !targetUserId) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    if (!isParent && !user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    getChronicleSummary(isParent ? targetUserId : undefined)
      .then((res) => {
        const chapters = res?.chapters ?? []
        setState({ loading: false, chapters, error: null })
      })
      .catch((err) => setState({ loading: false, chapters: [], error: err }))
  }

  useEffect(() => {
    let cancelled = false
    if (isParent && !targetUserId) {
      setState({ loading: false, chapters: [], error: null })
      return undefined
    }
    if (!isParent && !user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return undefined
    }
    getChronicleSummary(isParent ? targetUserId : undefined)
      .then((res) => {
        if (cancelled) return
        const chapters = res?.chapters ?? []
        setState({ loading: false, chapters, error: null })
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, chapters: [], error: err })
      })
    return () => {
      cancelled = true
    }
  }, [targetUserId, isParent, user?.id, user?.date_of_birth])

  // Sort chronologically so §I → §N reads left-to-right on the shelf, with
  // the current chapter on the right edge — same as flipping through a
  // book's spines.
  const sortedChapters = useMemo(
    () => [...(state.chapters || [])].sort((a, b) => a.chapter_year - b.chapter_year),
    [state.chapters],
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
    name: chapter.label || `Chapter ${idx + 1}`,
    icon: chapterMark(idx),
    chip: String(chapter.chapter_year),
    // Years aren't a completion concept — they're a calendar — so we hand
    // the spine a null progressPct. TomeSpine renders a thin hairline.
    progressPct: null,
    tier: chapter.is_current ? PROGRESS_TIER.rising : PROGRESS_TIER.nascent,
    ariaLabel: `${chapter.label || `Chapter ${idx + 1}`}, ${chapter.chapter_year}`,
  }))

  const activeChapter =
    sortedChapters.find((c) => String(c.chapter_year) === activeChapterId)
    || sortedChapters[sortedChapters.length - 1]

  if (state.loading) return <Loader />

  if (!isParent && !user?.date_of_birth) {
    return (
      <EmptyState>
        <p className="font-semibold mb-1">Set your date of birth</p>
        <p>A parent can set it on the Manage page — then birthdays, chapters, and yearly recaps can ink themselves.</p>
      </EmptyState>
    )
  }

  if (isParent && children.length === 0) {
    return (
      <EmptyState>
        <p className="font-semibold mb-1">No children yet</p>
        <p>Create a child account on the Manage page to start a yearbook.</p>
      </EmptyState>
    )
  }

  return (
    <div className="space-y-4">
      <p className="font-script text-sm text-ink-whisper text-center max-w-xl mx-auto">
        a lifelong journal of chapters, milestones, and daily entries · birthdays and graduations land here too
      </p>
      {isParent && (
        <div className="flex items-end justify-between gap-3">
          <SelectField
            id="yearbook-child-picker"
            label="Viewing"
            value={selectedChildId ?? ''}
            onChange={(e) => setSelectedChildId(parseInt(e.target.value, 10))}
            className="flex-1 max-w-xs"
          >
            {children.map((child) => (
              <option key={child.id} value={child.id}>
                {child.first_name || child.username}
              </option>
            ))}
          </SelectField>
          <Button
            variant="secondary"
            onClick={() => setShowAdd(true)}
            disabled={!selectedChildId}
          >
            Add memory
          </Button>
        </div>
      )}
      {shelfItems.length > 0 && (
        <TomeShelf
          items={shelfItems}
          activeId={activeChapterId}
          onSelect={setActiveChapterId}
          ariaLabel="Yearbook chapters"
        />
      )}
      {activeChapter && (
        <ChapterCard key={activeChapter.chapter_year} chapter={activeChapter} />
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
