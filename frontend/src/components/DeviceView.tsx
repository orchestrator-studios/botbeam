import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import ContentRenderer from './ContentRenderer';
import { TYPE_META, contentDetail, downloadMeta } from '../lib/contentMeta';
import type { Device } from '../types';

interface Props {
  deviceId: string;
  // Render this device directly instead of looking it up in the active list —
  // lets the pinned view show an archived device.
  device?: Device;
}

export default function DeviceView({ deviceId, device: deviceProp }: Props) {
  const { devices } = useBotBeam();
  const device = deviceProp ?? devices.find(d => d.id === deviceId);
  const content = device?.content ?? null;
  const [copied, setCopied] = useState(false);

  function copyBody() {
    if (!content) return;
    navigator.clipboard.writeText(content.body).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  function downloadBody() {
    if (!content) return;
    const { ext, mime } = downloadMeta(content.type);
    const safe = (device?.name || 'beam').replace(/[^\w.-]+/g, '_');
    const blob = new Blob([content.body], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safe}.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

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

  return (
    <div className="main display-view">
      <div className="device-info-bar">
        <span className="type-badge" style={{ borderColor: meta.color, color: meta.color }}>
          {meta.label}
        </span>
        {detail && <span className="meta-detail">{detail}</span>}
        <span className="device-info-actions">
          <button className="btn btn-ghost btn-sm" onClick={copyBody} title="Copy content to clipboard">
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={downloadBody} title="Download content to disk">
            Download
          </button>
        </span>
      </div>
      <ContentRenderer content={content} />
    </div>
  );
}
