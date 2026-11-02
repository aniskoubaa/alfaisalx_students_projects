import { create } from 'zustand';

export interface CodeState {
  /** File open in the editor, or null. */
  name: string | null;
  /** Text last saved on the robot. */
  orig: string;
  /** Text in the editor now. */
  text: string;
  sha1: string | null;
  status: string;
  loading: boolean;
  saving: boolean;
}

export const useCode = create<CodeState>()(() => ({
  name: null,
  orig: '',
  text: '',
  sha1: null,
  status: '',
  loading: false,
  saving: false,
}));

export const isCodeDirty = (s: CodeState): boolean => s.name !== null && s.text !== s.orig;
