import { useEffect, useState } from 'react'

import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { useAuth } from '../hooks/useApi'
import { getChronicleSummary } from '../api'
import ChapterCard from './yearbook/ChapterCard'

export default function Yearbook() {
  const { user } = useAuth()
  const [state, setState] = useState({ loading: true, chapters: [], error: null })

  useEffect(() => {
    let cancelled = false
    if (!user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    getChronicleSummary()
      .then((res) => {
        if (cancelled) return
        // api.get() returns raw data (res.json()), so res is already the payload
        const chapters = res?.chapters ?? []
        setState({ loading: false, chapters, error: null })
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, chapters: [], error: err })
      })
    return () => {
      cancelled = true
    }
  }, [user?.id, user?.date_of_birth])

  if (state.loading) return <Loader />

  if (!user?.date_of_birth) {
    return (
      <EmptyState>
        <p className="font-semibold mb-1">Set your date of birth</p>
        <p>A parent can set it on the Manage page. Then your Yearbook will start filling in.</p>
      </EmptyState>
    )
  }

  return (
    <div className="space-y-4">
      {state.chapters.map((chapter) => (
        <ChapterCard key={chapter.chapter_year} chapter={chapter} />
      ))}
    </div>
  )
}
