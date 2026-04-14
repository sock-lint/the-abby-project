/**
 * Loader — inked compass rose spinner. Matches the Hyrule Field Notes
 * aesthetic with a slowly rotating Sheikah ring.
 */
export default function Loader() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="relative w-10 h-10">
        <div
          className="absolute inset-0 border-2 border-sheikah-teal-deep border-t-transparent border-l-transparent rounded-full animate-spin"
          style={{ animationDuration: '1.1s' }}
        />
        <div
          className="absolute inset-1.5 border border-ink-page-shadow border-dashed rounded-full"
          style={{ animation: 'spin 3.8s linear infinite reverse' }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="w-1.5 h-1.5 rounded-full bg-sheikah-teal-deep" />
        </div>
      </div>
    </div>
  );
}
