import { create } from 'zustand';

/** What the person typed in each program's arguments box, kept while they move between screens. */
export const useArgs = create<{
  args: Record<string, string>;
  setArgs(name: string, value: string): void;
}>()((set, get) => ({
  args: {},
  setArgs: (name, value) => set({ args: { ...get().args, [name]: value } }),
}));
