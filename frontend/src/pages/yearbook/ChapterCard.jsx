export default function ChapterCard({ chapter }) {
  return (
    <div className="parchment-card p-4">
      <h3 className="text-lede font-serif">{chapter.label}</h3>
    </div>
  )
}
