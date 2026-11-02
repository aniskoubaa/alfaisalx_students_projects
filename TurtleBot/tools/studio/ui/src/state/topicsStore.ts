import { create } from 'zustand';
import type { TopicInfo } from '../api/setup-types';

export interface Watch {
  id: string;
  topic: string;
  data: unknown;
  rate: number | null;
}

export interface TopicsState {
  topics: TopicInfo[];
  loaded: boolean;
  loading: boolean;
  error: string | null;
  filter: string;
  watches: Record<string, Watch>;
  /** Topics whose watch request is on its way. */
  pending: string[];
}

export const initialTopics = (): TopicsState => ({
  topics: [],
  loaded: false,
  loading: false,
  error: null,
  filter: '',
  watches: {},
  pending: [],
});

export const useTopics = create<TopicsState>()(() => initialTopics());
