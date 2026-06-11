import { BotBeamProvider, useBotBeam } from './context/BotBeamContext';
import TabBar from './components/TabBar';
import Home from './components/Home';
import DeviceView from './components/DeviceView';
import Auth from './components/Auth';
import DebugPanel from './components/DebugPanel';

function AppContent() {
  const { user, authChecked, activeTab } = useBotBeam();

  if (!authChecked) return <div className="app-loading">Loading…</div>;
  if (!user) return <Auth />;

  return (
    <div className="app">
      <TabBar />
      <div className="app-body">
        {activeTab === 'home' ? <Home /> : <DeviceView key={activeTab} deviceId={activeTab} />}
      </div>
      <DebugPanel />
    </div>
  );
}

export default function App() {
  return (
    <BotBeamProvider>
      <AppContent />
    </BotBeamProvider>
  );
}
