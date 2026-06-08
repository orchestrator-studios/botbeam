// JWT bearer token storage — matches the kh / table-that convention
// (localStorage + Authorization: Bearer header, no cookies).
const KEY = 'botbeam_token';

export const getToken = (): string | null => localStorage.getItem(KEY);
export const setToken = (t: string): void => localStorage.setItem(KEY, t);
export const clearToken = (): void => localStorage.removeItem(KEY);
