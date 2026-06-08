import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import ContentRenderer from './ContentRenderer';
import { TYPE_META, contentDetail } from '../lib/contentMeta';

interface Props {
  deviceId: string;
}

export default function DeviceView({ deviceId }: Props) {
  const { devices } = useBotBeam();
  const device = devices.find(d => d.id === deviceId);
  const content = device?.content ?? null;
  const [showPayload, setShowPayload] = useState(false);

  if (!content) {
    return (
      <div className="main display-view">
        <div className="waiting">
          <div className="device-name">{device?.name ?? deviceId}</div>
          <p><span className="pulse" />Waiting for content...</p>
        </div>
      </div>
    );
  }

  const meta = TYPE_META[content.type];
  const detail = contentDetail(content);
  const isDropbox = !!device?.pickupMode;
  const pickupCount = device?.pickupCount ?? 0;
  const isPickedUp = isDropbox && device?.pickupMode === 'single' && pickupCount > 0;
  const pickups = device?.pickups ?? [];

  return (
    <div className="main display-view">
      <div className="device-info-bar">
        <span className="type-badge" style={{ borderColor: meta.color, color: meta.color }}>
          {meta.label}
        </span>
        {detail && <span className="meta-detail">{detail}</span>}
        {isDropbox && (
          <span className={`dropbox-badge ${isPickedUp ? 'picked-up' : ''}`}>
            {isPickedUp ? 'picked up' : device?.pickupMode === 'single' ? 'dropbox' : 'dropbox (multi)'}
          </span>
        )}
        {isDropbox && (
          <span className="meta-detail device-id-copy" title="Click to copy device ID" onClick={() => navigator.clipboard.writeText(device!.id)}>
            ID: {device!.id}
          </span>
        )}
        {isDropbox && pickupCount > 0 && (
          <span className="meta-detail">{pickupCount} pickup{pickupCount !== 1 ? 's' : ''}</span>
        )}
      </div>
      {isDropbox && !showPayload ? (
        <div className={`dropbox-package ${isPickedUp ? 'picked-up' : ''}`}>
          <div className="dropbox-overlay">
            <div className="dropbox-icon">{isPickedUp ? '\u{1F4ED}' : '\u{1F4E6}'}</div>
            <div className="dropbox-status">
              {isPickedUp
                ? `Picked up by ${pickups[0]?.pickedUpBy ?? 'unknown'}`
                : 'Awaiting pickup'}
            </div>
            {device?.pickupMode === 'multi' && pickupCount > 0 && (
              <div className="dropbox-pickup-count">{pickupCount} pickup{pickupCount !== 1 ? 's' : ''}</div>
            )}
            <button className="btn btn-ghost dropbox-reveal-btn" onClick={() => setShowPayload(true)}>
              Show payload
            </button>
            {pickups.length > 0 && (
              <div className="dropbox-history">
                {pickups.map((p, i) => (
                  <div key={i} className="pickup-entry">
                    {p.pickedUpBy} &middot; {new Date(p.pickedUpAt).toLocaleString()}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="dropbox-content-behind">
            <ContentRenderer content={content} />
          </div>
        </div>
      ) : isDropbox && showPayload ? (
        <>
          <button className="btn btn-ghost dropbox-hide-btn" onClick={() => setShowPayload(false)}>
            Hide payload
          </button>
          <ContentRenderer content={content} />
        </>
      ) : (
        <ContentRenderer content={content} />
      )}
    </div>
  );
}
