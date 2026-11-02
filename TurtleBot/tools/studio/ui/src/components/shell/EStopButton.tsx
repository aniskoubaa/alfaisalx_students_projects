import { OctagonX } from 'lucide-react';
import { useEstopKeys } from '../../lib/estopKeys';
import { triggerEstop } from '../../state/actions';

/**
 * The one loud element. Always visible in the top bar. Also bound to Esc, Space and
 * Ctrl+Shift+E (see lib/estopKeys.ts), so mount <EStopKeys /> once at the app root.
 */
export function EStopButton() {
  return (
    <button
      type="button"
      className="estop"
      onClick={() => void triggerEstop()}
      aria-label="Emergency stop. Shortcut: Escape or Space, or Control Shift E anywhere."
      title="Emergency stop. Esc or Space; Ctrl+Shift+E also works inside the code editor."
    >
      <OctagonX size={24} aria-hidden="true" />
      <span className="estop-text">
        <span className="estop-label">E-STOP</span>
        <span className="estop-hint">Esc or Space</span>
      </span>
    </button>
  );
}

export function EStopKeys() {
  useEstopKeys(() => void triggerEstop());
  return null;
}
