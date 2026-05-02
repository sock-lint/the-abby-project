import { useEffect, useState } from 'react'

import Button from '../components/Button'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { SelectField } from '../components/form'
import { useRole } from '../hooks/useRole'
import { getChildren, getChronicleSummary } from '../api'
import { normalizeList } from '../utils/api'
import ChapterCard from './yearbook/ChapterCard'
import ManualEntryFormModal from './yearbook/ManualEntryFormModal'

export default function Yearbook() {
  const { user, isParent } = useRole()
  const [state, setState] = useState({ loading: true, chapters: [], error: null })
  const [showAdd, setShowAdd] = useState(false)
  const [children, setChildren] = useState([])
  const [selectedChildId, setSelectedChildId] = useState(null)

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
      {state.chapters.map((chapter) => (
        <ChapterCard key={chapter.chapter_year} chapter={chapter} />
      ))}
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
