import { api } from './index';
import type {
  CreateKeyAnswer,
  DiagnosticsAnswer,
  HostKeyScan,
  JoinHotspotAnswer,
  LaptopNet,
  SetupKeyAnswer,
  SetupStatus,
  TeleopLimitsAnswer,
  TestLoginAnswer,
  TrustAnswer,
  WifiAddAnswer,
  WifiInfo,
  WifiStatusAnswer,
} from './setup-types';
import type { ApiResult, TrustedKey } from './types';

/** Calls for the setup wizard, Wi-Fi, tools and settings screens. All go through the shared client. */
export const setupApi = {
  setupStatus: (): Promise<ApiResult<SetupStatus>> => api().get<SetupStatus>('/api/setup_status'),
  scanHostKey: (host: string): Promise<ApiResult<HostKeyScan>> =>
    api().post<HostKeyScan>('/api/scan_host_key', { host }),
  trustHostKey: (key: string, label: string): Promise<ApiResult<TrustAnswer>> =>
    api().post<TrustAnswer>('/api/trust_host_key', { key, label, confirm: true }),
  untrustHostKey: (key: string): Promise<ApiResult<{ trusted: TrustedKey[] }>> =>
    api().post<{ trusted: TrustedKey[] }>('/api/untrust_host_key', { key, confirm: true }),
  createKey: (): Promise<ApiResult<CreateKeyAnswer>> =>
    api().post<CreateKeyAnswer>('/api/create_key', {}),
  setupKey: (host: string): Promise<ApiResult<SetupKeyAnswer>> =>
    api().post<SetupKeyAnswer>('/api/setup_key', host ? { host } : {}),
  testLogin: (host: string): Promise<ApiResult<TestLoginAnswer>> =>
    api().post<TestLoginAnswer>('/api/test_login', { host }),
  openTerminal: (): Promise<ApiResult<Record<string, never>>> =>
    api().post('/api/open_terminal', {}),

  laptopNet: (): Promise<ApiResult<LaptopNet>> => api().get<LaptopNet>('/api/laptop_net'),
  wifiInfo: (): Promise<ApiResult<WifiInfo>> =>
    api().post<WifiInfo>('/api/bridge', { cmd: 'wifi_info' }),
  wifiAdd: (ssid: string, psk: string, connectNow: boolean): Promise<ApiResult<WifiAddAnswer>> =>
    api().post<WifiAddAnswer>('/api/robot_wifi_add', {
      ssid,
      psk,
      connect_now: connectNow,
      confirm: true,
    }),
  wifiStatus: (nonce: string): Promise<ApiResult<WifiStatusAnswer>> =>
    api().post<WifiStatusAnswer>('/api/robot_wifi_status', { nonce }),
  wifiRemove: (name: string): Promise<ApiResult<Record<string, never>>> =>
    api().post('/api/robot_wifi_remove', { name, confirm: true }),
  joinHotspot: (): Promise<ApiResult<JoinHotspotAnswer>> =>
    api().post<JoinHotspotAnswer>('/api/join_hotspot', {}),
  laptopWifiSettings: (): Promise<ApiResult<Record<string, never>>> =>
    api().post('/api/laptop_wifi_settings', {}),

  diagnostics: (): Promise<ApiResult<DiagnosticsAnswer>> =>
    api().get<DiagnosticsAnswer>('/api/diagnostics'),
  teleopLimits: (): Promise<ApiResult<TeleopLimitsAnswer>> =>
    api().get<TeleopLimitsAnswer>('/api/teleop_limits'),
  saveTeleopLimits: (limits: {
    linear?: number;
    angular?: number;
  }): Promise<ApiResult<TeleopLimitsAnswer>> =>
    api().post<TeleopLimitsAnswer>('/api/teleop_limits', limits),
};
