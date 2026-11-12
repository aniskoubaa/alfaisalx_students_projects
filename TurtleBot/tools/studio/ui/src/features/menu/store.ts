/** What the Robot menu screen knows: the robot's file and check, and the document being edited. */
import { create } from 'zustand';
import type { MenuCheck, MenuGetAnswer } from '../../api';
import { checkMenu, getMenu, putMenu } from './api';
import { docFromCheck, emptyDoc, toYaml } from './model';
import type { MenuDoc } from './model';

export interface CheckedText {
  /** The generated file text the robot checked. */
  text: string;
  check: MenuCheck;
}

interface MenuStore {
  /** null until the first answer. */
  robot: MenuGetAnswer | null;
  robotError: string | null;
  doc: MenuDoc;
  /** The generated text of the document as it was loaded; the page is "changed" when it differs. */
  baseText: string;
  /** The robot's file is there but invalid, and the person has not chosen the standard menu yet. */
  blocked: boolean;
  lastCheck: CheckedText | null;
  checkError: string | null;
  checking: boolean;
  saving: boolean;
  saveError: string | null;
  load: () => Promise<void>;
  setDoc: (doc: MenuDoc) => void;
  startStandard: () => void;
  runCheck: () => Promise<void>;
  save: () => Promise<boolean>;
  reset: () => void;
}

const empty = {
  robot: null,
  robotError: null,
  doc: emptyDoc(),
  baseText: toYaml(emptyDoc()),
  blocked: false,
  lastCheck: null,
  checkError: null,
  checking: false,
  saving: false,
  saveError: null,
};

export const useMenu = create<MenuStore>((set, get) => ({
  ...empty,
  load: async () => {
    const r = await getMenu();
    if (!r.ok) {
      set({ robotError: r.error });
      return;
    }
    const good = r.check !== null && r.check.ok;
    const doc = good && r.check ? docFromCheck(r.check) : emptyDoc();
    const text = toYaml(doc);
    set({
      robot: r,
      robotError: null,
      doc,
      baseText: text,
      blocked: r.exists && !good,
      lastCheck: good && r.check ? { text, check: r.check } : null,
      checkError: null,
      saveError: null,
    });
  },
  setDoc: (doc) => set({ doc }),
  startStandard: () => {
    const doc = emptyDoc();
    set({ blocked: false, doc, lastCheck: null, checkError: null });
  },
  runCheck: async () => {
    const text = toYaml(get().doc);
    set({ checking: true, checkError: null });
    const r = await checkMenu(text);
    if (r.ok) set({ lastCheck: { text, check: r.check }, checking: false });
    else set({ checkError: r.error, checking: false });
  },
  save: async () => {
    const text = toYaml(get().doc);
    set({ saving: true, saveError: null });
    const r = await putMenu(text);
    if (!r.ok) {
      set({ saving: false, saveError: r.error });
      return false;
    }
    set({ saving: false });
    await get().load();
    return true;
  },
  reset: () => set({ ...empty, doc: emptyDoc() }),
}));

/** The robot's last check when it describes exactly the current document, else null. */
export function currentCheck(s: Pick<MenuStore, 'lastCheck' | 'doc'>): MenuCheck | null {
  return s.lastCheck && s.lastCheck.text === toYaml(s.doc) ? s.lastCheck.check : null;
}
