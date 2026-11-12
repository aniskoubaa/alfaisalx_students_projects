/** Typed calls for the Robot menu screen. */
import { api } from '../../api';
import type { ApiResult, BridgeAnswers } from '../../api';

const T = { timeoutMs: 20_000 };

export const getMenu = (): Promise<ApiResult<BridgeAnswers['menu_get']>> =>
  api().bridge('menu_get', {}, T);

/** Asks the robot's checker about a text, without touching the menu file. */
export const checkMenu = (text: string): Promise<ApiResult<BridgeAnswers['menu_check']>> =>
  api().bridge('menu_check', { text }, T);

/** Always sends confirm:true; the dialog in the interface is the confirmation. */
export const putMenu = (text: string): Promise<ApiResult<BridgeAnswers['menu_put']>> =>
  api().bridge('menu_put', { text, confirm: true }, T);
