import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChapterCard from './ChapterCard'

describe('ChapterCard', () => {
  it('current-chapter shows live progress bar', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2025, label: 'Freshman Year', grade: 9,
      is_current: true, is_post_hs: false,
      stats: { projects_completed: 3, coins_earned: 200 },
      entries: [],
    }} />)
    expect(screen.getByText('Freshman Year')).toBeInTheDocument()
    expect(screen.getByText(/projects completed/i)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('past-chapter shows frozen stats, no progress bar', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2024, label: 'Grade 8', grade: 8,
      is_current: false, is_post_hs: false,
      stats: { projects_completed: 5 },
      entries: [],
    }} />)
    expect(screen.getByText('Grade 8')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('post-HS chapter renders age-based label', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2029, label: 'Age 18 · 2029-30', grade: 13,
      is_current: false, is_post_hs: true,
      stats: {},
      entries: [],
    }} />)
    expect(screen.getByText('Age 18 · 2029-30')).toBeInTheDocument()
  })
})
