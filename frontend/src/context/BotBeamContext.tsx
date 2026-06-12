import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import type { Device, WSEvent } from '../types';
import { botbeamApi } from '../lib/api/botbeamApi';
import { settings } from '../config/settings';
import { getToken, setToken, clearToken } from '../lib/authStorage';

interface LogEntry {
  time: string;
  event: string;
  detail: string;
}

interface BotBeamContextType {
  user: string | null;
  authChecked: boolean;
  devices: Device[];
  displays: Device[];
  lockboxes: Device[];
  activeTab: string;
  pinnedId: string | null;
  wsLog: LogEntry[];
  showDebug: boolean;
  connected: boolean;
  pulsingTab: string | null;
  version: string;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  switchTab: (id: string) => void;
  addDevice: (name: string) => Promise<void>;
  removeDevice: (id: string) => Promise<void>;
  archiveDevice: (id: string) => Promise<void>;
  unarchiveDevice: (id: string) => Promise<void>;
  resetDevices: () => Promise<void>;
  pinDevice: (id: string) => void;
  unpin: () => void;
  toggleDebug: () => void;
  proxyUrl: (url: string) => string;
}

const BotBeamContext = createContext<BotBeamContextType | undefined>(undefined);

// eslint-disable-next-line react-refresh/only-export-components
export function useBotBeam() {
  const context = useContext(BotBeamContext);
  if (!context) throw new Error('useBotBeam must be used within a BotBeamProvider');
  return context;
}

// Pinning is a property of THIS browser instance (a kiosk screen like the
// kitchen computer), not of the account — so it lives in localStorage.
const PIN_KEY = 'botbeam_pin';

// Default display first, then by creation time — matches the server's ordering
// so WS-driven inserts land in the same place a reload would put them.
function sortDevices(list: Device[]): Device[] {
  return [...list].sort((a, b) => {
    if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1;
    return a.createdAt < b.createdAt ? -1 : 1;
  });
}

export function BotBeamProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [activeTab, setActiveTab] = useState('home');
  const [pinnedId, setPinnedId] = useState<string | null>(() => localStorage.getItem(PIN_KEY));
  const [wsLog, setWsLog] = useState<LogEntry[]>([]);
  const [showDebug, setShowDebug] = useState(false);
  const [connected, setConnected] = useState(false);
  const [pulsingTab, setPulsingTab] = useState<string | null>(null);
  const [version, setVersion] = useState('');
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wsRef = useRef<WebSocket | null>(null);
  const initialVersion = useRef('');
  // Mirror of pinnedId for the WS handler closure — changing the pin must not
  // tear down and reconnect the socket.
  const pinnedRef = useRef<string | null>(localStorage.getItem(PIN_KEY));
  const pinParamApplied = useRef(false);

  // --- Auth ---

  const login = useCallback(async (email: string, password: string) => {
    const r = await botbeamApi.login(email, password);
    setToken(r.access_token);
    setUser(r.email);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const r = await botbeamApi.register(email, password);
    setToken(r.access_token);
    setUser(r.email);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setDevices([]);
    setActiveTab('home');
  }, []);

  // Check stored token on load
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    botbeamApi.me()
      .then((u) => setUser(u.email))
      .catch(() => { clearToken(); setUser(null); })
      .finally(() => setAuthChecked(true));
  }, []);

  // --- Device actions ---

  const switchTab = useCallback((id: string) => setActiveTab(id), []);

  const addDevice = useCallback(async (name: string) => {
    if (!user) return;
    await botbeamApi.createDevice(name);
  }, [user]);

  const removeDevice = useCallback(async (id: string) => {
    if (!user) return;
    await botbeamApi.deleteDevice(id);
  }, [user]);

  const archiveDevice = useCallback(async (id: string) => {
    if (!user) return;
    await botbeamApi.archiveDevice(id);
  }, [user]);

  const unarchiveDevice = useCallback(async (id: string) => {
    if (!user) return;
    await botbeamApi.unarchiveDevice(id);
  }, [user]);

  const resetDevices = useCallback(async () => {
    if (!user) return;
    await botbeamApi.resetDevices();
  }, [user]);

  // --- Pinning (kiosk mode) ---

  const pinDevice = useCallback((id: string) => {
    localStorage.setItem(PIN_KEY, id);
    pinnedRef.current = id;
    setPinnedId(id);
  }, []);

  const unpin = useCallback(() => {
    localStorage.removeItem(PIN_KEY);
    pinnedRef.current = null;
    setPinnedId(null);
    // Strip a ?pin= kiosk bookmark so a reload doesn't immediately re-pin.
    const url = new URL(window.location.href);
    if (url.searchParams.has('pin')) {
      url.searchParams.delete('pin');
      window.history.replaceState({}, '', url);
    }
  }, []);

  // Resolve a ?pin=<id-or-name> kiosk bookmark once devices are known. Keeps
  // retrying on device updates until the named display exists, then applies once.
  useEffect(() => {
    if (pinParamApplied.current || devices.length === 0) return;
    const param = new URLSearchParams(window.location.search).get('pin');
    if (!param) {
      pinParamApplied.current = true;
      return;
    }
    const target = devices.find((d) => d.kind !== 'lockbox'
      && (d.id === param || d.name.toLowerCase() === param.toLowerCase()));
    if (target) {
      pinParamApplied.current = true;
      pinDevice(target.id);
    }
  }, [devices, pinDevice]);

  const toggleDebug = useCallback(() => setShowDebug((prev) => !prev), []);

  const proxyUrl = useCallback((url: string) => botbeamApi.proxyUrl(url), []);

  // --- Load devices when logged in ---

  const refreshState = useCallback(async () => {
    setDevices(sortDevices(await botbeamApi.getDevices()));
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    botbeamApi.getDevices()
      .then((d) => { if (!cancelled) setDevices(sortDevices(d)); })
      .catch(() => { if (!cancelled) console.error('Initial state load failed'); });
    return () => { cancelled = true; };
  }, [user]);

  // --- WebSocket (authenticated via ?token=) ---

  useEffect(() => {
    if (!user) return;

    let reconnectTimer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    let ws: WebSocket;
    let isReconnect = false;

    function pulse(id: string) {
      clearTimeout(pulseTimer.current);
      setPulsingTab(id);
      pulseTimer.current = setTimeout(() => setPulsingTab(null), 800);
    }

    function connect() {
      if (cancelled) return;
      const token = getToken();
      if (!token) return;
      ws = new WebSocket(`${settings.wsUrl}/ws?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        if (isReconnect) refreshState().catch(() => {});
        isReconnect = true;
      };

      ws.onmessage = (e) => {
        const msg: WSEvent = JSON.parse(e.data);

        switch (msg.event) {
          case 'device_created':
            setDevices((prev) => prev.some((d) => d.id === msg.device.id)
              ? prev : sortDevices([...prev, msg.device]));
            // Lockboxes are stashes — they land in the panel, not the screen.
            // A pinned (kiosk) instance never follows beams to other devices.
            if (msg.device.kind !== 'lockbox' && !pinnedRef.current) {
              setActiveTab(msg.device.id);
              pulse(msg.device.id);
            }
            break;
          case 'device_updated':
            setDevices((prev) => prev.map((d) => d.id === msg.device.id ? msg.device : d));
            if (msg.device.kind !== 'lockbox' && !pinnedRef.current) {
              setActiveTab(msg.device.id);
              pulse(msg.device.id);
            }
            break;
          case 'device_unarchived':
            setDevices((prev) => prev.some((d) => d.id === msg.device.id)
              ? prev.map((d) => d.id === msg.device.id ? msg.device : d)
              : sortDevices([...prev, msg.device]));
            pulse(msg.device.id);
            break;
          case 'device_archived':
            setDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setActiveTab((prev) => prev === msg.deviceId ? 'home' : prev);
            break;
          case 'device_deleted':
            setDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setActiveTab((prev) => prev === msg.deviceId ? 'home' : prev);
            break;
          case 'devices_reset':
            // The default display survives a reset (cleared) — reload from the server.
            refreshState().catch(() => setDevices([]));
            setActiveTab('home');
            break;
        }

        setWsLog((prev) => [...prev, {
          time: new Date().toLocaleTimeString(),
          event: msg.event,
          detail: 'device' in msg ? msg.device.name : 'deviceId' in msg ? msg.deviceId : '',
        }]);
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) reconnectTimer = setTimeout(connect, 2000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, [user, refreshState]);

  // --- Version polling: reload when a new deploy is detected ---

  useEffect(() => {
    function check() {
      fetch(`${settings.apiUrl}/health`).then((r) => r.json()).then((d) => {
        const v = d.version ?? '';
        if (!initialVersion.current) {
          initialVersion.current = v;
          setVersion(v);
        } else if (v && v !== initialVersion.current) {
          window.location.reload();
        }
      }).catch(() => {});
    }
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  const displays = devices.filter((d) => d.kind !== 'lockbox');
  const lockboxes = devices.filter((d) => d.kind === 'lockbox');

  const value: BotBeamContextType = {
    user,
    authChecked,
    devices,
    displays,
    lockboxes,
    activeTab,
    pinnedId,
    wsLog,
    showDebug,
    connected,
    pulsingTab,
    version,
    login,
    register,
    logout,
    switchTab,
    addDevice,
    removeDevice,
    archiveDevice,
    unarchiveDevice,
    resetDevices,
    pinDevice,
    unpin,
    toggleDebug,
    proxyUrl,
  };

  return <BotBeamContext.Provider value={value}>{children}</BotBeamContext.Provider>;
}
