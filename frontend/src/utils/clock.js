import { STORAGE_KEYS } from '../constants/storage';

/**
 * Clock-in venture memory. Clock-in is the most-repeated action in the app
 * and most kids clock into the same project every day, so both clock-in
 * surfaces (ClockPage and the FAB's ClockPane) remember the last venture and
 * preselect it — or auto-select when only one project is active — instead of
 * demanding a fresh pick every time.
 */

export const ACTIVE_PROJECT_STATUSES = ['active', 'in_progress'];

export function activeProjectsOf(projects) {
  return projects.filter((p) => ACTIVE_PROJECT_STATUSES.includes(p.status));
}

/** Persist the venture just clocked into. Best-effort — storage may be unavailable. */
export function rememberClockProject(projectId) {
  try {
    localStorage.setItem(STORAGE_KEYS.LAST_CLOCK_PROJECT, String(projectId));
  } catch { /* private mode etc. — the picker just won't be preselected */ }
}

/**
 * Default selection for a clock-in picker: the remembered venture when it is
 * still in the active list, else the only active venture, else '' (unset).
 * Returns a stringified id to match <option value>.
 */
export function defaultClockProjectId(activeProjects) {
  let remembered = null;
  try {
    remembered = localStorage.getItem(STORAGE_KEYS.LAST_CLOCK_PROJECT);
  } catch { /* storage unavailable */ }
  const match = activeProjects.find((p) => String(p.id) === remembered);
  if (match) return String(match.id);
  if (activeProjects.length === 1) return String(activeProjects[0].id);
  return '';
}

/** The remembered venture as a project object, or null when it no longer applies. */
export function rememberedClockProject(activeProjects) {
  let remembered = null;
  try {
    remembered = localStorage.getItem(STORAGE_KEYS.LAST_CLOCK_PROJECT);
  } catch { /* storage unavailable */ }
  return activeProjects.find((p) => String(p.id) === remembered) || null;
}
