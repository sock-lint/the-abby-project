import { describe, expect, it } from 'vitest';
import {
  buttonDanger,
  buttonGhost,
  buttonPrimary,
  buttonSecondary,
  buttonSuccess,
  cardSurface,
  cardSurfacePlain,
  headingDisplay,
  headingScript,
  inputClass,
} from './styles.js';

describe('styles module', () => {
  it.each([
    ['inputClass', inputClass],
    ['buttonPrimary', buttonPrimary],
    ['buttonSecondary', buttonSecondary],
    ['buttonDanger', buttonDanger],
    ['buttonSuccess', buttonSuccess],
    ['buttonGhost', buttonGhost],
    ['cardSurface', cardSurface],
    ['cardSurfacePlain', cardSurfacePlain],
    ['headingDisplay', headingDisplay],
    ['headingScript', headingScript],
  ])('%s exports a non-empty string of Tailwind classes', (_name, value) => {
    expect(typeof value).toBe('string');
    expect(value.length).toBeGreaterThan(0);
  });
});
