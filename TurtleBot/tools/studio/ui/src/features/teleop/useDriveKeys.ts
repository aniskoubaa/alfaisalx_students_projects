import { useEffect } from 'react';
import { DRIVE_KEYS } from './controller';
import { isArmed, keyDown, keyUp, releaseAll } from './driver';

/** Where a key press belongs to something else (typing, sliders, the code editor, a dialog). */
const NOT_FOR_DRIVING =
  'input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable="true"],[contenteditable=""],.cm-editor,[role=dialog],[role=listbox],[role=menu]';

export interface DriveKeyEvent {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  target: EventTarget | null;
}

/** Which drive direction does this key press mean, or null when the key is not for driving. */
export function driveDirFor(e: DriveKeyEvent) {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  const dir = DRIVE_KEYS[e.key.toLowerCase()];
  if (!dir) return null;
  const t = e.target instanceof Element ? e.target : null;
  if (t?.closest(NOT_FOR_DRIVING)) return null;
  return dir;
}

/**
 * W, A, S, D and the arrow keys drive while this hook is mounted (the Live screen) and driving is
 * armed. A key up is always honoured, wherever focus is, so a key can never stay "held".
 */
export function useDriveKeys(): void {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (!isArmed()) return;
      const dir = driveDirFor(e);
      if (!dir) return;
      e.preventDefault();
      keyDown(dir);
    };
    const up = (e: KeyboardEvent) => {
      const dir = DRIVE_KEYS[e.key.toLowerCase()];
      if (dir) keyUp(dir);
    };
    document.addEventListener('keydown', down);
    document.addEventListener('keyup', up);
    return () => {
      document.removeEventListener('keydown', down);
      document.removeEventListener('keyup', up);
      releaseAll();
    };
  }, []);
}
