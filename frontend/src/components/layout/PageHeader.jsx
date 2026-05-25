export default function PageHeader({
  title,
  kicker,
  actions,
  className = '',
}) {
  return (
    <header className={`flex items-start gap-3 ${className}`}>
      <div className="flex-1 min-w-0">
        {kicker && (
          <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
            {kicker}
          </div>
        )}
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          {title}
        </h1>
      </div>
      {actions && (
        <div className="flex items-center gap-2 shrink-0 pt-1">{actions}</div>
      )}
    </header>
  );
}
