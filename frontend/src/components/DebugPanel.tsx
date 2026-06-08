import { useEffect, useRef } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

export default function DebugPanel() {
  const { wsLog, showDebug, toggleDebug } = useBotBeam();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [wsLog.length]);

  return (
    <>
      <button className="debug-toggle" onClick={toggleDebug} title="Toggle debug panel">
        WS {wsLog.length}
      </button>
      {showDebug && (
        <div className="debug-panel">
          <div className="debug-header">
            <span>WebSocket Log</span>
            <button className="debug-close" onClick={toggleDebug}>&times;</button>
          </div>
          <div className="debug-entries">
            {wsLog.length === 0 && (
              <div className="debug-empty">No events yet</div>
            )}
            {wsLog.map((entry, i) => (
              <div key={i} className="debug-entry">
                <span className="debug-time">{entry.time}</span>
                <span className={`debug-event debug-event-${entry.event.replace('_', '-')}`}>{entry.event}</span>
                <span className="debug-detail">{entry.detail}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  );
}
