import type { CatalogEntry, ProgramDescription } from '../api';

/** Programs Studio always treats as moving the robot (same list as Studio 1.3). */
export const MOTION_DEFAULT: readonly string[] = [
  'drive_test.py',
  'motion_shapes.py',
  'motion_test.sh',
  'more_shapes.py',
  'wall_approach.py',
  'keep_distance.py',
  'campaign.sh',
];

export function isMotionProgram(
  path: string,
  catalog: Record<string, CatalogEntry>,
  desc: Record<string, ProgramDescription>,
  extra: readonly string[] = [],
): boolean {
  const n = path.split('/').pop() ?? path;
  const c = catalog[n];
  const d = desc[n];
  return MOTION_DEFAULT.includes(n) || extra.includes(n) || !!c?.moves || !!d?.moves_detected;
}

/** Built-in motion programs cannot be un-marked by the user. */
export function isBuiltinMotion(name: string, catalog: Record<string, CatalogEntry>): boolean {
  return MOTION_DEFAULT.includes(name) || !!catalog[name]?.moves;
}

export function isHelperProgram(name: string, catalog: Record<string, CatalogEntry>): boolean {
  return catalog[name]?.category === 'helper';
}
