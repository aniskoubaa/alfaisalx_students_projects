import { useEffect } from 'react';

export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  shiftKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  repeat: boolean;
  target: EventTarget | null;
}

const TYPING =
  'input:not([type=checkbox]):not([type=radio]),textarea,select,[contenteditable="true"],[contenteditable=""]';
const ACTIVATES_ON_SPACE =
  'button,a,summary,input,[role=tab],[role=menuitem],[role=option],[role=radio],[role=checkbox],[role=switch],[role=button]';

/**
 * Should this key press fire the E-STOP?
 * Ctrl+Shift+E works everywhere, also inside the code editor. Esc and Space work
 * everywhere except while typing, and Space is left alone on things it activates.
 */
export function isEstopKey(e: KeyLike): boolean {
  if (e.repeat) return false;
  if (e.ctrlKey && e.shiftKey && (e.key === 'E' || e.key === 'e')) return true;
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  const t = e.target instanceof Element ? e.target : null;
  if (t?.closest(TYPING)) return false;
  if (e.key === 'Escape') return true;
  if (e.key === ' ' && !t?.closest(ACTIVATES_ON_SPACE)) return true;
  return false;
}

/** Listen for the E-STOP keys on the whole page. */
export function useEstopKeys(fire: () => void): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!isEstopKey(e)) return;
      e.preventDefault();
      fire();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [fire]);
}
