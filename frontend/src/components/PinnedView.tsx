import { useEffect, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import type { Device } from '../types';
import DeviceView from './DeviceView';

// Kiosk mode: this browser instance is pinned to a single display (e.g. the
// kitchen screen). No tab strip, no lockbox panel — just the device's content,
// live-updating, with a slim bar to identify the device and unpin.
//
// The pin is a bookmark: it keeps showing the device even when archived.
// Archived devices aren't in the active list, so when the device drops out we
// fetch its snapshot by id — only a 404 (deleted) gives up.
export default function PinnedView() {
  const { pinnedId, devices, sharedDevices, unpin, connected } = useBotBeam();
  // A kiosk can be pinned to an owned display or one shared with it — watch both
  // lists so live beams refresh the screen either way.
  const live = devices.find((d) => d.id === pinnedId) ?? sharedDevices.find((d) => d.id === pinnedId);
  const [snapshot, setSnapshot] = useState<Device | null>(null);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    if (live || !pinnedId) {
      setSnapshot(null);
      setDeleted(false);
      return;
    }
    let cancelled = false;
    botbeamApi.getDevice(pinnedId)
      .then((d) => { if (!cancelled) { setSnapshot(d); setDeleted(false); } })
      .catch(() => { if (!cancelled) { setSnapshot(null); setDeleted(true); } });
    return () => { cancelled = true; };
    // device lists are deps so a delete/unshare (no `live` transition) still re-checks.
  }, [live, pinnedId, devices, sharedDevices]);

  const device = live ?? snapshot;

  return (
    <div className="app">
      <div className="pinned-bar">
        <span className="pinned-name">
          <span className={`ws-dot ${connected ? 'on' : ''}`} title={connected ? 'Connected' : 'Disconnected'} />
          {device ? device.name : 'BotBeam'}
          {device?.archivedAt && <span className="pinned-archived">archived</span>}
        </span>
        <button className="pinned-unpin" onClick={unpin} title="Unpin this browser and show all tabs">
          Unpin
        </button>
      </div>
      <div className="app-body">
        {device ? (
          <DeviceView key={device.id} deviceId={device.id} device={device} />
        ) : (
          <div className="main display-view">
            <div className="waiting">
              <div className="device-name">{deleted ? 'Display not available' : 'Loading…'}</div>
              {deleted && <p>The pinned display was deleted. Unpin to see all tabs.</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
