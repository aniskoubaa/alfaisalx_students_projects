import * as RT from '@radix-ui/react-toast';
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useToasts } from '../../state/feedback';
import type { ToastKind } from '../../state/feedback';

const ICON: Record<ToastKind, ReactNode> = {
  ok: <CircleCheck size={18} aria-hidden="true" />,
  info: <Info size={18} aria-hidden="true" />,
  warn: <TriangleAlert size={18} aria-hidden="true" />,
  error: <CircleAlert size={18} aria-hidden="true" />,
};

export function ToastHost() {
  const items = useToasts((s) => s.items);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <RT.Provider swipeDirection="right" label="Notifications">
      {items.map((t) => (
        <RT.Root
          key={t.id}
          className={`toast toast-${t.kind}`}
          type={t.kind === 'error' ? 'foreground' : 'background'}
          duration={t.kind === 'error' ? 10000 : 5000}
          onOpenChange={(open) => {
            if (!open) dismiss(t.id);
          }}
        >
          <span className="toast-icon">{ICON[t.kind]}</span>
          <RT.Description className="toast-text">{t.text}</RT.Description>
          <RT.Close className="btn btn-ghost btn-icon btn-sm" aria-label="Dismiss notification">
            <X size={14} aria-hidden="true" />
          </RT.Close>
        </RT.Root>
      ))}
      <RT.Viewport className="toast-viewport" />
    </RT.Provider>
  );
}
