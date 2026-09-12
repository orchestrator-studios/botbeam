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
  userId: number | null;
  authChecked: boolean;
  devices: Device[];
  displays: Device[];
  lockboxes: Device[];
  sharedDevices: Device[];
  activeTab: string;
  pinnedId: string | null;
  wsLog: LogEntry[];
  showDebug: boolean;
  connected: boolean;
  pulsingTab: string | null;
  version: string;
  // Bumped on every ledger_sessions WS event — the Sessions view refetches on change.
  ledgerBump: number;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  switchTab: (id: string) => void;
  addDevice: (name: string) => Promise<void>;
  removeDevice: (id: string) => Promise<void>;
  archiveDevice: (id: string) => Promise<void>;
  unarchiveDevice: (id: string) => Promise<void>;
  resetDevices: () => Promise<void>;
  shareDevice: (id: string, email: string) => Promise<Device>;
  unshareDevice: (id: string, email: string) => Promise<Device>;
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

// Shared-with-me devices: just by creation time (no default among them).
function sortShared(list: Device[]): Device[] {
  return [...list].sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1));
}

// Upsert a shared device from a WS payload. Owner-driven content updates carry
// no ownerEmail (it's not theirs to send), so keep the email we already have.
function upsertShared(prev: Device[], dev: Device): Device[] {
  const existing = prev.find((d) => d.id === dev.id);
  if (existing) {
    const merged = { ...dev, ownerEmail: dev.ownerEmail ?? existing.ownerEmail };
    return prev.map((d) => (d.id === dev.id ? merged : d));
  }
  return sortShared([...prev, dev]);
}

export function BotBeamProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [userId, setUserId] = useState<number | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [sharedDevices, setSharedDevices] = useState<Device[]>([]);
  const [activeTab, setActiveTab] = useState('home');
  const [pinnedId, setPinnedId] = useState<string | null>(() => localStorage.getItem(PIN_KEY));
  const [wsLog, setWsLog] = useState<LogEntry[]>([]);
  const [showDebug, setShowDebug] = useState(false);
  const [connected, setConnected] = useState(false);
  const [pulsingTab, setPulsingTab] = useState<string | null>(null);
  const [version, setVersion] = useState('');
  const [ledgerBump, setLedgerBump] = useState(0);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wsRef = useRef<WebSocket | null>(null);
  const initialVersion = useRef('');
  // Mirror of pinnedId for the WS handler closure — changing the pin must not
  // tear down and reconnect the socket.
  const pinnedRef = useRef<string | null>(localStorage.getItem(PIN_KEY));
  const pinParamApplied = useRef(false);
  // Mirror of userId for the WS closure — the handler routes each device event
  // to the owned list or the shared list by comparing ownerId to my id.
  const userIdRef = useRef<number | null>(null);

  // --- Auth ---

  const identify = useCallback((email: string, id: number) => {
    userIdRef.current = id;
    setUserId(id);
    setUser(email);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await botbeamApi.login(email, password);
    setToken(r.access_token);
    identify(r.email, r.user_id);
  }, [identify]);

  const register = useCallback(async (email: string, password: string) => {
    const r = await botbeamApi.register(email, password);
    setToken(r.access_token);
    identify(r.email, r.user_id);
  }, [identify]);

  const logout = useCallback(() => {
    clearToken();
    userIdRef.current = null;
    setUser(null);
    setUserId(null);
    setDevices([]);
    setSharedDevices([]);
    setActiveTab('home');
  }, []);

  // Check stored token on load
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    botbeamApi.me()
      .then((u) => identify(u.email, u.user_id))
      .catch(() => { clearToken(); setUser(null); })
      .finally(() => setAuthChecked(true));
  }, [identify]);

  // --- Device actions ---

  const switchTab = useCallback((id: string) => setActiveTab(id), []);

  const addDevice = useCallback(async (name: string) => {
    if (!user) return;
    await botbeamApi.beamNew(name);
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

  // Share/unshare return the owner-facing device (with its updated grantee list);
  // patch it into the local list so the share dialog reflects the change at once.
  const shareDevice = useCallback(async (id: string, email: string) => {
    const dev = await botbeamApi.shareDevice(id, email);
    setDevices((prev) => prev.map((d) => (d.id === id ? dev : d)));
    return dev;
  }, []);

  const unshareDevice = useCallback(async (id: string, email: string) => {
    const dev = await botbeamApi.unshareDevice(id, email);
    setDevices((prev) => prev.map((d) => (d.id === id ? dev : d)));
    return dev;
  }, []);

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
    if (pinParamApplied.current) return;
    if (devices.length === 0 && sharedDevices.length === 0) return;
    const param = new URLSearchParams(window.location.search).get('pin');
    if (!param) {
      pinParamApplied.current = true;
      return;
    }
    // A kiosk can pin its own display or one shared with it.
    const match = (d: Device) => d.kind !== 'lockbox'
      && (d.id === param || d.name.toLowerCase() === param.toLowerCase());
    const target = devices.find(match) ?? sharedDevices.find(match);
    if (target) {
      pinParamApplied.current = true;
      pinDevice(target.id);
    }
  }, [devices, sharedDevices, pinDevice]);

  const toggleDebug = useCallback(() => setShowDebug((prev) => !prev), []);

  const proxyUrl = useCallback((url: string) => botbeamApi.proxyUrl(url), []);

  // --- Load devices when logged in ---

  const refreshState = useCallback(async () => {
    const [own, shared] = await Promise.all([
      botbeamApi.getDevices(),
      botbeamApi.getSharedDevices(),
    ]);
    setDevices(sortDevices(own));
    setSharedDevices(sortShared(shared));
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    Promise.all([botbeamApi.getDevices(), botbeamApi.getSharedDevices()])
      .then(([own, shared]) => {
        if (cancelled) return;
        setDevices(sortDevices(own));
        setSharedDevices(sortShared(shared));
      })
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

        // A device event is about an owned device or one shared with me; route
        // by ownerId (absent on legacy payloads → treat as mine).
        const isMine = (d: Device) => d.ownerId === undefined || d.ownerId === userIdRef.current;

        switch (msg.event) {
          case 'device_created':
            // Only ever fired for the owner (a fresh device has no grantees yet).
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
            if (isMine(msg.device)) {
              setDevices((prev) => prev.map((d) => d.id === msg.device.id ? msg.device : d));
              if (msg.device.kind !== 'lockbox' && !pinnedRef.current) {
                setActiveTab(msg.device.id);
                pulse(msg.device.id);
              }
            } else {
              // Owner beamed to a device shared with me — refresh it in place,
              // but don't yank my view to it.
              setSharedDevices((prev) => upsertShared(prev, msg.device));
              pulse(msg.device.id);
            }
            break;
          case 'device_unarchived':
            if (isMine(msg.device)) {
              setDevices((prev) => prev.some((d) => d.id === msg.device.id)
                ? prev.map((d) => d.id === msg.device.id ? msg.device : d)
                : sortDevices([...prev, msg.device]));
            } else {
              setSharedDevices((prev) => upsertShared(prev, msg.device));
            }
            pulse(msg.device.id);
            break;
          case 'device_archived':
            // Removed from whichever list holds it (owner's tabs or my shared list).
            setDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setSharedDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setActiveTab((prev) => prev === msg.deviceId ? 'home' : prev);
            break;
          case 'device_deleted':
            setDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setSharedDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setActiveTab((prev) => prev === msg.deviceId ? 'home' : prev);
            break;
          case 'device_shared':
            // A device was just shared with me — add it to my shared list.
            setSharedDevices((prev) => upsertShared(prev, msg.device));
            pulse(msg.device.id);
            break;
          case 'device_unshared':
            // My access was revoked — drop it (a pin to it will now 404, showing
            // the kiosk's "not available" state).
            setSharedDevices((prev) => prev.filter((d) => d.id !== msg.deviceId));
            setActiveTab((prev) => prev === msg.deviceId ? 'home' : prev);
            break;
          case 'devices_reset':
            // The default display survives a reset (cleared) — reload from the server.
            refreshState().catch(() => setDevices([]));
            setActiveTab('home');
            break;
          case 'ledger_sessions':
            // A session fact changed somewhere — the Sessions view refetches the board.
            setLedgerBump((b) => b + 1);
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
    userId,
    authChecked,
    devices,
    displays,
    lockboxes,
    sharedDevices,
    activeTab,
    pinnedId,
    wsLog,
    showDebug,
    connected,
    pulsingTab,
    version,
    ledgerBump,
    login,
    register,
    logout,
    switchTab,
    addDevice,
    removeDevice,
    archiveDevice,
    unarchiveDevice,
    resetDevices,
    shareDevice,
    unshareDevice,
    pinDevice,
    unpin,
    toggleDebug,
    proxyUrl,
  };

  return <BotBeamContext.Provider value={value}>{children}</BotBeamContext.Provider>;
}
