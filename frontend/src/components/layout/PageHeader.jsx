export default function PageHeader({
  title,
  kicker,
  actions,
  className = '',
}) {
  return (
    <header className={`flex flex-wrap items-start gap-3 font-body ${className}`}>
      <div className="flex-1 min-w-0">
        {kicker && (
          <div className="font-body font-semibold text-sheikah-teal-deep text-caption mb-1">
            {kicker}
          </div>
        )}
        <h1 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight tracking-tight break-words">
          {title}
        </h1>
      </div>
      {actions && (
        <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2 pt-1 sm:w-auto sm:shrink-0">{actions}</div>
      )}
    </header>
  );
}
