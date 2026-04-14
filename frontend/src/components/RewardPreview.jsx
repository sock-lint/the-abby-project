export default function RewardPreview({ breakdown }) {
  if (!breakdown) return null;

  const { base_money, base_coins, effort_level, timeliness_multiplier, final_money, final_coins } = breakdown;

  return (
    <div className="text-xs text-white/60 space-y-0.5">
      <div className="flex items-center gap-1">
        <span>${final_money}</span>
        <span className="text-white/30">+</span>
        <span>{final_coins}c</span>
      </div>
      <div className="text-white/40">
        Base ${base_money} / {base_coins}c
        {' '}× effort {effort_level}
        {' '}× {timeliness_multiplier}x
      </div>
    </div>
  );
}
