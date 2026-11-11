import { Suspense, lazy, useEffect } from 'react';
import { Banners } from './components/shell/Banners';
import { EStopKeys } from './components/shell/EStopButton';
import { EventsDrawer } from './components/shell/EventsDrawer';
import { Sidebar } from './components/shell/Sidebar';
import { StoppedScreen } from './components/shell/StoppedScreen';
import { TopBar } from './components/shell/TopBar';
import { DialogHost, Spinner, TooltipProvider, ToastHost } from './components/ui';
import { FeatureHost } from './features/FeatureHost';
import { ArmedBar } from './features/teleop/ArmedBar';
import { isCodeDirty, useCode } from './state/code';
import { useRoute } from './state/router';
import { startF2Runtime } from './state/f2runtime';
import { startRuntime } from './state/runtime';
import { useStudio } from './state/store';
import { Code } from './screens/Code';
import { ComingSoon } from './screens/ComingSoon';
import { Files } from './screens/Files';
import { Overview } from './screens/Overview';
import { Programs } from './screens/Programs';
import { Live } from './screens/live/Live';
import { Maps } from './screens/maps/Maps';
import { Logs } from './screens/logs/Logs';
import { Settings } from './screens/settings/Settings';
import { Tools } from './screens/tools/Tools';
import { Topics } from './screens/topics/Topics';
import { Wifi } from './screens/wifi/Wifi';
import { WizardDialog } from './screens/wizard/WizardDialog';

const Charts = lazy(() => import('./screens/charts/Charts'));

function Screen() {
  const route = useRoute();
  switch (route.path) {
    case '/overview':
      return <Overview />;
    case '/programs':
      return <Programs />;
    case '/code':
      return <Code />;
    case '/files':
      return <Files />;
    case '/live':
      return <Live />;
    case '/maps':
      return <Maps />;
    case '/charts':
      return (
        <Suspense
          fallback={
            <div className="page" role="status">
              <Spinner /> Loading charts
            </div>
          }
        >
          <Charts />
        </Suspense>
      );
    case '/logs':
      return <Logs />;
    case '/wifi':
      return <Wifi />;
    case '/topics':
      return <Topics />;
    case '/tools':
      return <Tools />;
    case '/settings':
      return <Settings />;
    default:
      return <ComingSoon route={route} />;
  }
}

export function App({ runtime = true }: { runtime?: boolean }) {
  const stopped = useStudio((s) => s.stopped);
  const route = useRoute();

  useEffect(() => {
    if (!runtime) return;
    const stopRuntime = startRuntime();
    const stopF2 = startF2Runtime();
    return () => {
      stopF2();
      stopRuntime();
    };
  }, [runtime]);

  // Closing the tab or reloading with unsaved code asks first, whichever screen is open.
  const dirty = useCode(isCodeDirty);
  useEffect(() => {
    if (!dirty) return;
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  useEffect(() => {
    document.title = `${route.label} - TurtleBot Studio`;
  }, [route.label]);

  if (stopped) return <StoppedScreen />;
  return (
    <TooltipProvider>
      <EStopKeys />
      <div className="app">
        <ArmedBar />
        <TopBar />
        <Banners />
        <div className="app-body">
          <Sidebar />
          <main className="main" id="main" tabIndex={-1}>
            <Screen />
          </main>
          <EventsDrawer />
        </div>
      </div>
      <WizardDialog />
      <FeatureHost />
      <DialogHost />
      <ToastHost />
    </TooltipProvider>
  );
}
