export function hapticTap() {
  navigator.vibrate?.(10);
}

export function hapticSuccess() {
  navigator.vibrate?.([10, 50, 20]);
}
