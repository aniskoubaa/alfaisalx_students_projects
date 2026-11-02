import { api } from '../api';

/** Link to a page of the classic interface, carrying this session's token. */
export const classicHref = (path: string): string => api().pageUrl(path);
