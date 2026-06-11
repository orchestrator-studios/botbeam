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
      </div>
      <ContentRenderer content={content} />
    </div>
  );
}
