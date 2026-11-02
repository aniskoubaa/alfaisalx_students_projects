import * as RT from '@radix-ui/react-tooltip';
import type { ReactElement, ReactNode } from 'react';

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <RT.Provider delayDuration={400} skipDelayDuration={200}>
      {children}
    </RT.Provider>
  );
}

export function Tooltip({
  content,
  children,
  side = 'bottom',
}: {
  content: ReactNode;
  children: ReactElement;
  side?: 'top' | 'right' | 'bottom' | 'left';
}) {
  return (
    <RT.Root>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content className="tooltip" side={side} sideOffset={6}>
          {content}
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  );
}
