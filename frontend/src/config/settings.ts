const isProd = import.meta.env.MODE === 'production';
const devHost = window.location.hostname === 'localhost' ? 'localhost' : window.location.hostname;

export const settings = {
  apiUrl: isProd ? '' : `http://${devHost}:4888`,
  publicUrl: isProd ? `${window.location.protocol}//${window.location.host}` : `http://${devHost}:4888`,
  wsUrl: isProd
    ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
    : `ws://${devHost}:4888`,
};
