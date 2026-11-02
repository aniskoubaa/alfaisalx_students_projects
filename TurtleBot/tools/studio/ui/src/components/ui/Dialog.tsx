import * as RD from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { useDialogs } from '../../state/feedback';
import type { DialogRequest, DialogTone } from '../../state/feedback';
import { Button } from './Button';
import { Checkbox } from './Form';

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  tone?: DialogTone;
  size?: 'md' | 'lg';
}

/**
 * A modal dialog. Esc does not close it: Esc is the E-STOP key everywhere in Studio.
 * The top bar stays clickable (see .topbar in shell.css), so the E-STOP is reachable.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  tone = 'primary',
  size = 'md',
}: DialogProps) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="dialog-overlay" />
        <RD.Content
          className={`dialog dialog-${tone} dialog-${size}`}
          onEscapeKeyDown={(e) => e.preventDefault()}
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <header className="dialog-head">
            <RD.Title className="dialog-title">{title}</RD.Title>
            <RD.Close asChild>
              <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Close">
                <X size={16} aria-hidden="true" />
              </button>
            </RD.Close>
          </header>
          {description ? (
            <RD.Description asChild>
              <div className="dialog-desc">{description}</div>
            </RD.Description>
          ) : null}
          <div className="dialog-body">{children}</div>
          {footer ? <footer className="dialog-foot">{footer}</footer> : null}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: DialogTone;
  /** The confirm button stays off until this box is ticked. */
  requireCheck?: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  const {
    open,
    title,
    body,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    tone = 'primary',
    requireCheck,
    pending,
    onConfirm,
    onCancel,
  } = props;
  const [checked, setChecked] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
      title={title}
      tone={tone}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            disabled={!!requireCheck && !checked}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="dialog-text">{body}</div>
      {requireCheck ? (
        <div className="dialog-check">
          <Checkbox
            label={requireCheck}
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
        </div>
      ) : null}
      {tone === 'caution' ? (
        <p className="dim small">Stay close and keep the E-STOP in reach (Esc or Space).</p>
      ) : null}
    </Dialog>
  );
}

/** Shows the dialogs asked for by confirm() and inform() in state/feedback. */
export function DialogHost() {
  const stack = useDialogs((s) => s.stack);
  const close = useDialogs((s) => s.close);
  const top: DialogRequest | undefined = stack[stack.length - 1];
  if (!top) return null;
  if (top.kind === 'confirm') {
    const done = (ok: boolean) => {
      close(top);
      top.resolve(ok);
    };
    return (
      <ConfirmDialog
        key={stack.length + top.title}
        open
        title={top.title}
        body={top.body}
        confirmLabel={top.confirmLabel}
        cancelLabel={top.cancelLabel}
        tone={top.tone}
        requireCheck={top.requireCheck}
        onConfirm={() => done(true)}
        onCancel={() => done(false)}
      />
    );
  }
  const finish = () => {
    close(top);
    top.resolve();
  };
  return (
    <Dialog
      key={stack.length + top.title}
      open
      onOpenChange={(o) => {
        if (!o) finish();
      }}
      title={top.title}
      tone={top.tone}
      footer={
        <Button variant="primary" onClick={finish}>
          {top.closeLabel ?? 'Close'}
        </Button>
      }
    >
      <div className="dialog-text">{top.body}</div>
    </Dialog>
  );
}
