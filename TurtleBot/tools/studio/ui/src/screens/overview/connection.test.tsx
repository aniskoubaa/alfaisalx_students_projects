import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { DialogHost, TooltipProvider } from '../../components/ui';
import { routeWords } from '../../lib/connView';
import { useStudio } from '../../state/store';
import { connectedStatus, installApi, resetStores } from '../../test/helpers';
import { ConnectionPanel } from './ConnectionPanel';

function wrap() {
  return render(
    <TooltipProvider>
      <ConnectionPanel />
      <DialogHost />
    </TooltipProvider>,
  );
}

beforeEach(() => {
  resetStores();
  installApi(() => ({ ok: true }));
});

describe('route words', () => {
  it('never shows the internal names', () => {
    expect(routeWords('cable')).toBe('Ethernet cable');
    expect(routeWords('wifi')).toBe('Wi-Fi');
    expect(routeWords('hotspot')).toBe('robot hotspot');
    expect(routeWords('custom')).toBe('typed address');
    expect(routeWords(null)).toBeNull();
    expect(routeWords(undefined)).toBeNull();
  });
});

describe('connection card', () => {
  it('shows the full card while disconnected', () => {
    wrap();
    expect(screen.getByLabelText('Robot address (optional)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discover' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Change robot' })).toBeNull();
  });

  it('shows a short summary while connected and reveals the tools on request', async () => {
    connectedStatus();
    useStudio.getState().dispatch({ ev: 'conn', state: 'connected', host: 'x', via: 'custom' });
    wrap();
    expect(screen.getByText('Typed address'.toLowerCase())).toBeInTheDocument();
    expect(screen.queryByText('custom')).toBeNull();
    expect(screen.getByText('Connected since')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Robot address (optional)')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Discover' })).toBeNull();
    const change = screen.getByRole('button', { name: 'Change robot' });
    expect(change).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(change);
    expect(change).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Robot address (optional)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discover' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search the whole network' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Setup wizard' })).toBeInTheDocument();
  });
});
