/** Presentation boundaries use the server's normalized bonus, never day counts. */
export function streakBonusStage(bonus) {
  if (!bonus || typeof bonus.active_today !== 'boolean'
    || !Number.isFinite(bonus.intensity) || bonus.intensity < 0 || bonus.intensity > 1
    || !Number.isFinite(bonus.check_in_multiplier) || bonus.check_in_multiplier < 1
    || !Number.isSafeInteger(bonus.check_in_coins) || bonus.check_in_coins < 0
    || !Number.isFinite(bonus.drop_bonus) || bonus.drop_bonus < 0 || bonus.drop_bonus > 1) return 'unknown';
  if (!bonus.active_today) {
    return bonus.intensity === 0 && bonus.check_in_multiplier === 1
      && bonus.check_in_coins === 0 && bonus.drop_bonus === 0 ? 'dormant-ember' : 'unknown';
  }
  if (bonus.intensity <= 0) return 'unknown';
  return bonus.intensity === 1 ? 'maximum-blaze' : bonus.intensity >= 0.5 ? 'strong-flame' : 'small-flame';
}
