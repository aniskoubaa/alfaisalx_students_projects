/** What the Routes screen knows: the route list and the trip status, both read from the robot. */
import { create } from 'zustand';
import type { RoutesList, TripStatusAnswer } from '../../api';
import { listRoutes, tripStatus } from './api';

interface RoutesStore {
  /** null until the first answer. */
  list: RoutesList | null;
  listError: string | null;
  trip: TripStatusAnswer | null;
  tripError: string | null;
  loadRoutes: () => Promise<void>;
  loadTrip: () => Promise<void>;
  reset: () => void;
}

const empty = { list: null, listError: null, trip: null, tripError: null };

export const useRoutes = create<RoutesStore>((set) => ({
  ...empty,
  loadRoutes: async () => {
    const r = await listRoutes();
    if (r.ok) set({ list: r, listError: null });
    else set({ listError: r.error });
  },
  loadTrip: async () => {
    const r = await tripStatus(40);
    if (r.ok) set({ trip: r, tripError: null });
    else set({ tripError: r.error });
  },
  reset: () => set({ ...empty }),
}));
