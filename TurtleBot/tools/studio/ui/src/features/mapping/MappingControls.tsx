import { CircleStop, Eraser, MapPinned, Save } from 'lucide-react';
import { useState } from 'react';
import { Badge, Button, ConfirmDialog, Spinner } from '../../components/ui';
import { notify } from '../../state/feedback';
import { useStudio } from '../../state/store';
import { disarm } from '../teleop/driver';
import { resetMapping, startMapping, stopMapping } from './api';
import { allowedActions, formatAge, isBusy, stateTone, stateWord } from './model';
import { SaveMapDialog } from './SaveMapDialog';
import { useMapping } from './store';
import type { ApiResult, MappingInfo } from '../../api';

function apply(r: ApiResult<MappingInfo>, failure: string): void {
  if (r.ok) {
    const { ok: _ok, ...info } = r;
    void _ok;
    useMapping.getState().setInfo(info);
  } else {
    notify('error', failure + ' ' + r.error);
  }
}

/** The state, the buttons that fit it, and the last error and saved map in words. */
export function MappingControls() {
  const info = useMapping((s) => s.info);
  const connected = useStudio((s) => s.conn.state === 'connected');
  const [saveOpen, setSaveOpen] = useState(false);
  const [stopAsk, setStopAsk] = useState(false);
  const [pending, setPending] = useState<'start' | 'stop' | 'reset' | null>(null);

  const allowed = allowedActions(info, connected);
  const busy = isBusy(info);

  const run = async (
    op: 'start' | 'stop' | 'reset',
    call: () => Promise<ApiResult<MappingInfo>>,
    failure: string,
  ) => {
    setPending(op);
    if (op !== 'reset') disarm('Mapping is changing state.');
    apply(await call(), failure);
    setPending(null);
  };

  const onStop = () => {
    if (info?.unsaved) setStopAsk(true);
    else void run('stop', stopMapping, 'Could not stop mapping.');
  };

  const disabledReason = (a: { enabled: boolean; reason: string }) =>
    a.enabled ? undefined : a.reason;

  return (
    <div className="mapping-controls">
      <div className="mapping-row">
        <span data-testid="mapping-state" className="mapping-state" role="status">
          <Badge tone={stateTone(info)} icon={busy ? <Spinner size={12} /> : undefined}>
            {stateWord(info)}
          </Badge>
        </span>
        <div className="mapping-buttons" role="group" aria-label="Mapping actions">
          <Button
            variant="primary"
            icon={<MapPinned size={16} aria-hidden="true" />}
            disabled={!allowed.start.enabled}
            title={disabledReason(allowed.start)}
            loading={pending === 'start'}
            onClick={() => void run('start', startMapping, 'Could not start mapping.')}
          >
            Start mapping
          </Button>
          <Button
            icon={<Save size={16} aria-hidden="true" />}
            disabled={!allowed.save.enabled}
            title={disabledReason(allowed.save)}
            onClick={() => setSaveOpen(true)}
          >
            Save map
          </Button>
          <Button
            icon={<CircleStop size={16} aria-hidden="true" />}
            disabled={!allowed.stop.enabled}
            title={disabledReason(allowed.stop)}
            loading={pending === 'stop'}
            onClick={onStop}
          >
            Stop mapping
          </Button>
          <Button
            icon={<Eraser size={16} aria-hidden="true" />}
            disabled={!allowed.reset.enabled}
            title={disabledReason(allowed.reset)}
            loading={pending === 'reset'}
            onClick={() => void run('reset', resetMapping, 'Could not clear the error.')}
          >
            Clear error
          </Button>
        </div>
      </div>

      {!allowed.start.enabled && info?.state === 'idle' ? (
        <p className="dim small" data-testid="start-reason">
          {allowed.start.reason}
        </p>
      ) : null}
      {info?.last_error ? (
        <p className="mapping-error" role="alert" data-testid="mapping-error">
          Last error: {info.last_error}
        </p>
      ) : null}
      {info?.last_saved ? (
        <p className="dim small" data-testid="mapping-saved">
          Last saved map: {info.last_saved.name} ({formatAge(info.last_saved.t)}).
        </p>
      ) : null}
      {info?.unsaved && info.state === 'mapping' ? (
        <p className="dim small">This map is not saved yet.</p>
      ) : null}

      <SaveMapDialog
        key={saveOpen ? 'open' : 'closed'}
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
      />
      <ConfirmDialog
        open={stopAsk}
        title="Stop mapping?"
        tone="danger"
        body="This map is not saved. Stop and lose it?"
        confirmLabel="Stop and lose the map"
        cancelLabel="Keep mapping"
        onCancel={() => setStopAsk(false)}
        onConfirm={() => {
          setStopAsk(false);
          void run('stop', stopMapping, 'Could not stop mapping.');
        }}
      />
    </div>
  );
}
