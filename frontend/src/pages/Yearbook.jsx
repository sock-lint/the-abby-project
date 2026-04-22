import { useEffect, useState } from 'react'

import Button from '../components/Button'
import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { useAuth } from '../hooks/useApi'
import { getChronicleSummary } from '../api'
import ChapterCard from './yearbook/ChapterCard'
import ManualEntryFormModal from './yearbook/ManualEntryFormModal'

export default function Yearbook() {
  const { user } = useAuth()
  const [state, setState] = useState({ loading: true, chapters: [], error: null })
  const [showAdd, setShowAdd] = useState(false)

  const fetchSummary = () => {
    const isParentUser = user?.role === 'parent'
    if (!isParentUser && !user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    getChronicleSummary()
      .then((res) => {
        // api.get() returns raw data (res.json()), so res is already the payload
        const chapters = res?.chapters ?? []
        setState({ loading: false, chapters, error: null })
      })
      .catch((err) => setState({ loading: false, chapters: [], error: err }))
  }

  useEffect(() => {
    let cancelled = false
    const isParentUser = user?.role === 'parent'
    if (!isParentUser && !user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    getChronicleSummary()
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
  }, [user?.id, user?.date_of_birth, user?.role])

  if (state.loading) return <Loader />

  const isParent = user?.role === 'parent'

  if (!isParent && !user?.date_of_birth) {
    return (
      <EmptyState>
        <p className="font-semibold mb-1">Set your date of birth</p>
        <p>A parent can set it on the Manage page. Then your Yearbook will start filling in.</p>
      </EmptyState>
    )
  }

  const canAdd = isParent

  return (
    <div className="space-y-4">
      {canAdd && (
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => setShowAdd(true)}>
            Add memory
          </Button>
        </div>
      )}
      {state.chapters.map((chapter) => (
        <ChapterCard key={chapter.chapter_year} chapter={chapter} />
      ))}
      {showAdd && (
        <ManualEntryFormModal
          userId={user?.id}
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
