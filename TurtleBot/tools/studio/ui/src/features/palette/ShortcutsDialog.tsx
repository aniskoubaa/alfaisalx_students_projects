import { Dialog, Button } from '../../components/ui';
import { usePalette } from './paletteCommands';

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? 'Cmd' : 'Ctrl';

const ROWS: Array<{ keys: string[]; what: string }> = [
  { keys: ['Esc'], what: 'E-STOP, from anywhere except while typing in a box' },
  { keys: ['Space'], what: 'E-STOP, when no button or box has focus' },
  { keys: ['Ctrl', 'Shift', 'E'], what: 'E-STOP, also inside the code editor' },
  { keys: [MOD, 'K'], what: 'Open the command palette' },
  { keys: ['?'], what: 'Show this list' },
  {
    keys: ['W', 'A', 'S', 'D'],
    what: 'Drive, on the Live screen, after you arm driving. Release to stop',
  },
  { keys: ['↑', '↓', '←', '→'], what: 'Drive, same as W, S, A, D' },
  { keys: ['+', '−'], what: 'Zoom the map, when the map has focus' },
];

export function ShortcutsDialog() {
  const open = usePalette((s) => s.shortcuts);
  const setOpen = usePalette((s) => s.setShortcuts);
  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      title="Keyboard shortcuts"
      footer={
        <Button variant="primary" onClick={() => setOpen(false)}>
          Close
        </Button>
      }
    >
      <table className="keys-table" aria-label="Keyboard shortcuts">
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.what}>
              <th scope="row">
                {r.keys.map((k, i) => (
                  <span key={k + i}>
                    {i > 0 ? ' ' : ''}
                    <kbd>{k}</kbd>
                  </span>
                ))}
              </th>
              <td>{r.what}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Dialog>
  );
}
