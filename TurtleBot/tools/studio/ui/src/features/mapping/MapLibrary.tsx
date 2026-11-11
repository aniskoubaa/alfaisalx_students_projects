import { Download, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { MapEntry } from '../../api';
import {
  Button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  Field,
  Input,
  Panel,
  Spinner,
  Table,
} from '../../components/ui';
import { notify } from '../../state/feedback';
import { deleteMap, downloadMap, fetchPreview, listMaps, renameMap } from './api';
import {
  filesSummary,
  formatBytes,
  formatSaved,
  resolutionText,
  sizeOfEntry,
  validMapName,
} from './model';
import { useMapping } from './store';

/** The preview picture of a saved map, fetched with the token and shown from an object URL. */
function Preview({ name }: { name: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    void fetchPreview(name).then((r) => {
      if (!alive) return;
      if (!r.ok) {
        setError(r.error);
        return;
      }
      if (typeof URL.createObjectURL !== 'function') {
        setError('This browser cannot show the picture.');
        return;
      }
      made = URL.createObjectURL(r.blob);
      setUrl(made);
    });
    return () => {
      alive = false;
      if (made && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(made);
    };
  }, [name]);
  if (error)
    return (
      <p className="dim small" role="status">
        No preview for {name}. {error}
      </p>
    );
  if (!url)
    return (
      <p className="dim small" role="status">
        <Spinner size={14} /> Loading the preview of {name}
      </p>
    );
  return <img className="map-preview" src={url} alt={`Preview of the map ${name}`} />;
}

function RenameDialog({
  entry,
  taken,
  onDone,
  onClose,
}: {
  entry: MapEntry;
  taken: string[];
  onDone: () => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(entry.name);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const check = validMapName(name);
  const same = name === entry.name;
  const dup = !same && taken.includes(name);
  const message = !check.ok ? check.message : dup ? `A map named ${name} already exists.` : null;

  const submit = async () => {
    if (message || same || busy) return;
    setBusy(true);
    setError(null);
    const r = await renameMap(entry.name, name);
    setBusy(false);
    if (r.ok) {
      notify('ok', `Renamed ${entry.name} to ${name}.`);
      onDone();
    } else setError(r.error);
  };

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o && !busy) onClose();
      }}
      title={`Rename ${entry.name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={!!message || same}
            loading={busy}
          >
            Rename map
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field
          label="New name"
          hint="Letters, digits, hyphens and underscores. Up to 48 characters."
          error={same ? null : (message ?? error)}
        >
          {(p) => (
            <Input
              {...p}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
              maxLength={64}
              autoFocus
            />
          )}
        </Field>
      </form>
    </Dialog>
  );
}

/** The maps saved on the robot: preview, rename, download and delete. */
export function MapLibrary({ connected = true }: { connected?: boolean }) {
  const [maps, setMaps] = useState<MapEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<MapEntry | null>(null);
  const [deleting, setDeleting] = useState<MapEntry | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const savedAt = useMapping((s) => s.info?.last_saved?.t ?? null);

  const apply = useCallback((r: Awaited<ReturnType<typeof listMaps>>) => {
    if (r.ok) {
      setMaps(r.maps);
      setError(null);
    } else setError(r.error);
  }, []);

  const load = useCallback(async () => apply(await listMaps()), [apply]);

  const refresh = async () => {
    setLoading(true);
    await load();
    setLoading(false);
  };

  // Load when the screen opens, when the robot connects and after a new map is saved.
  useEffect(() => {
    if (!connected) return;
    let alive = true;
    void listMaps().then((r) => {
      if (alive) apply(r);
    });
    return () => {
      alive = false;
    };
  }, [connected, savedAt, apply]);

  const shown = selected && maps?.some((m) => m.name === selected) ? selected : null;

  const download = async (m: MapEntry) => {
    setBusy(m.name);
    const r = await downloadMap(m.name);
    setBusy(null);
    if (!r.ok) notify('error', `Could not download ${m.name}. ${r.error}`);
  };

  const doDelete = async () => {
    const m = deleting;
    if (!m) return;
    setBusy(m.name);
    const r = await deleteMap(m.name);
    setBusy(null);
    setDeleting(null);
    if (r.ok) {
      notify('ok', `Deleted the map ${m.name}.`);
      void load();
    } else notify('error', `Could not delete ${m.name}. ${r.error}`);
  };

  return (
    <Panel
      title="Saved maps"
      actions={
        <Button
          size="sm"
          icon={<RefreshCw size={14} aria-hidden="true" />}
          loading={loading}
          disabled={!connected}
          onClick={() => void refresh()}
        >
          Refresh
        </Button>
      }
    >
      {!connected ? (
        <p className="dim small">Not connected to the robot. Connect to see its saved maps.</p>
      ) : error ? (
        <p className="mapping-error" role="alert">
          Could not read the saved maps. {error}
        </p>
      ) : maps === null ? (
        <p className="dim small" role="status">
          <Spinner size={14} /> Loading the saved maps
        </p>
      ) : maps.length === 0 ? (
        <EmptyState compact title="No saved maps yet">
          Start mapping, drive around, then save the map to see it here.
        </EmptyState>
      ) : (
        <Table label="Saved maps" className="map-table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Size</th>
              <th scope="col">Detail</th>
              <th scope="col">Saved</th>
              <th scope="col">Files</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {maps.map((m) => (
              <tr
                key={m.name}
                data-testid={`map-row-${m.name}`}
                className={m.name === shown ? 'is-selected' : ''}
              >
                <th scope="row">
                  <button
                    type="button"
                    className="link-btn"
                    aria-pressed={m.name === shown}
                    aria-label={`Show the preview of ${m.name}`}
                    onClick={() => setSelected(m.name === shown ? null : m.name)}
                  >
                    {m.name}
                  </button>
                </th>
                <td>{sizeOfEntry(m)}</td>
                <td>{resolutionText(m.resolution)}</td>
                <td>{formatSaved(m.mtime)}</td>
                <td title={formatBytes(m.bytes)}>
                  {filesSummary(m.files)}, {formatBytes(m.bytes)}
                </td>
                <td>
                  <div className="map-actions">
                    <Button
                      size="sm"
                      icon={<Pencil size={14} aria-hidden="true" />}
                      aria-label={`Rename ${m.name}`}
                      disabled={busy === m.name}
                      onClick={() => setRenaming(m)}
                    >
                      Rename
                    </Button>
                    <Button
                      size="sm"
                      icon={<Download size={14} aria-hidden="true" />}
                      aria-label={`Download ${m.name}`}
                      loading={busy === m.name}
                      onClick={() => void download(m)}
                    >
                      Download
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      icon={<Trash2 size={14} aria-hidden="true" />}
                      aria-label={`Delete ${m.name}`}
                      disabled={busy === m.name}
                      onClick={() => setDeleting(m)}
                    >
                      Delete
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {shown ? (
        <div className="map-preview-box" data-testid="map-preview">
          <Preview key={shown} name={shown} />
        </div>
      ) : null}

      {renaming ? (
        <RenameDialog
          key={renaming.name}
          entry={renaming}
          taken={(maps ?? []).map((m) => m.name)}
          onClose={() => setRenaming(null)}
          onDone={() => {
            if (selected === renaming.name) setSelected(null);
            setRenaming(null);
            void load();
          }}
        />
      ) : null}
      <ConfirmDialog
        open={deleting !== null}
        title={`Delete ${deleting?.name ?? 'map'}?`}
        tone="danger"
        body={`The files of the map ${deleting?.name ?? ''} will be removed from the robot. This cannot be undone.`}
        confirmLabel="Delete map"
        pending={deleting !== null && busy === deleting.name}
        onConfirm={() => void doDelete()}
        onCancel={() => setDeleting(null)}
      />
    </Panel>
  );
}
