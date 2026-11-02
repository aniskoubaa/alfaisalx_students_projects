import { Copy, Download } from 'lucide-react';
import { useId } from 'react';
import { Button } from '../../components/ui';
import { copyText, saveTextFile } from '../../lib/clip';
import { useAsyncAction } from '../../lib/useAsync';
import { notify } from '../../state/feedback';

/** Diagnostics text with Copy and Save as file. Passwords, keys and the session token are already removed by Studio. */
export function DiagnosticsBody({ text }: { text: string }) {
  const id = useId();
  const copy = useAsyncAction(async () => {
    const ok = await copyText(text);
    notify(
      ok ? 'ok' : 'warn',
      ok ? 'Diagnostics copied.' : 'Could not copy by itself. Select the text and press Ctrl+C.',
    );
  });
  return (
    <div className="diag">
      <p>
        Paste this into your message when you ask for help. Passwords, keys and the session token
        are removed. Read it once before you send it.
      </p>
      <div className="row">
        <Button
          variant="primary"
          icon={<Copy size={16} aria-hidden="true" />}
          loading={copy.pending}
          onClick={() => void copy.run()}
        >
          Copy
        </Button>
        <Button
          icon={<Download size={16} aria-hidden="true" />}
          onClick={() => {
            saveTextFile('studio-diagnostics.txt', text);
            notify('ok', 'Saved studio-diagnostics.txt.');
          }}
        >
          Save as file
        </Button>
      </div>
      <label htmlFor={id} className="sr-only">
        Diagnostics text
      </label>
      <textarea id={id} className="diag-text" readOnly spellCheck={false} value={text} />
    </div>
  );
}
