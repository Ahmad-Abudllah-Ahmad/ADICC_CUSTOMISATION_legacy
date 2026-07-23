// @ts-nocheck
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CollaborationModule from './CollaborationModule';
import { COLLAB_COLORS, pickColor } from './types';
import { ConnectionStatus } from './components/ConnectionStatus';
import { CollaborationBar } from './components/CollaborationBar';
import type { ConnectionStatusInfo } from './hooks/useConnectionStatus';
import type { CollabUser } from './types';

// The hub fetches the project list, presence and locks. Stub the network
// layer so the page renders deterministically against an empty backend —
// the static chrome (header, settings, how-it-works) renders regardless,
// and the live sections fall back to their honest empty states.
vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(() => Promise.resolve([])),
  apiPost: vi.fn(() => Promise.resolve({})),
  apiPatch: vi.fn(() => Promise.resolve({})),
  apiDelete: vi.fn(() => Promise.resolve(undefined)),
  getErrorMessage: (e: unknown) => String(e),
}));

vi.mock('@/features/collab_locks', () => ({
  usePresenceWebSocket: () => ({ status: 'idle', users: [], lastEvent: null }),
  listMyLocks: () => Promise.resolve([]),
}));

function renderHub() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CollaborationModule />
    </QueryClientProvider>,
  );
}

describe('CollaborationModule', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should render the page header', () => {
    renderHub();
    // Regex matchers tolerate identity-marker ZWJ/ZWNJ trailing the visible text.
    expect(screen.getByText(/Real-time Collaboration/)).toBeInTheDocument();
    expect(screen.getByText(/Discuss, share viewpoints/)).toBeInTheDocument();
  });

  it('should expose the collapsible how-it-works + settings panel', () => {
    renderHub();
    expect(
      screen.getByText(/How real-time editing works/),
    ).toBeInTheDocument();
  });

  it('should reveal feature cards when the panel is expanded', () => {
    renderHub();
    fireEvent.click(screen.getByText(/How real-time editing works/));
    expect(screen.getByText(/Peer-to-Peer Sync/)).toBeInTheDocument();
    expect(screen.getByText(/CRDT Conflict Resolution/)).toBeInTheDocument();
    expect(screen.getByText('Presence Awareness')).toBeInTheDocument();
  });

  it('should render display name input inside the expanded panel', () => {
    renderHub();
    fireEvent.click(screen.getByText(/How real-time editing works/));
    expect(screen.getByText('Your display name')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Your name')).toBeInTheDocument();
  });

  it('should save display name to localStorage', () => {
    renderHub();
    fireEvent.click(screen.getByText(/How real-time editing works/));
    const input = screen.getByPlaceholderText('Your name');
    fireEvent.change(input, { target: { value: 'Test User' } });
    fireEvent.click(screen.getByText('Save'));
    expect(localStorage.getItem('oe_collab_name')).toBe('Test User');
  });

  it('should show color palette inside the expanded panel', () => {
    renderHub();
    fireEvent.click(screen.getByText(/How real-time editing works/));
    expect(screen.getByText(/User Colors/)).toBeInTheDocument();
  });

  it('should show disclaimer inside the expanded panel', () => {
    renderHub();
    fireEvent.click(screen.getByText(/How real-time editing works/));
    // The module intro card mentions WebRTC too, so assert at least one match
    // (the expanded panel's disclaimer) instead of exactly one.
    expect(screen.getAllByText(/peer-to-peer WebRTC/).length).toBeGreaterThanOrEqual(1);
  });

  it('should show an honest empty state when there are no projects', async () => {
    renderHub();
    // The projects query resolves to [] asynchronously; once settled the page
    // drops the loading spinner and shows the honest no-projects empty state.
    expect(
      await screen.findByText(/No project to collaborate on yet/),
    ).toBeInTheDocument();
  });
});

describe('Collaboration types', () => {
  it('should have 8 predefined colors', () => {
    expect(COLLAB_COLORS).toHaveLength(8);
  });

  it('should have unique colors', () => {
    expect(new Set(COLLAB_COLORS).size).toBe(COLLAB_COLORS.length);
  });

  it('pickColor should cycle through colors', () => {
    expect(pickColor(0)).toBe(COLLAB_COLORS[0]);
    expect(pickColor(7)).toBe(COLLAB_COLORS[7]);
    expect(pickColor(8)).toBe(COLLAB_COLORS[0]); // wraps around
    expect(pickColor(15)).toBe(COLLAB_COLORS[7]);
  });
});

describe('Collaboration module registration', () => {
  it('should be registered in MODULE_REGISTRY', async () => {
    const { MODULE_REGISTRY } = await import('../_registry');
    const mod = MODULE_REGISTRY.find((m) => m.id === 'collaboration');
    expect(mod).toBeDefined();
    // Module name string in registry includes identity-marker ZWJ/ZWNJ;
    // assert via prefix match rather than strict equality.
    expect(mod!.name).toMatch(/^Real-time Collaboration/);
    expect(mod!.routes[0].path).toBe('/collaboration');
  }, 15000);
});

// --- ConnectionStatus component tests ---

describe('ConnectionStatus', () => {
  const baseInfo: ConnectionStatusInfo = {
    status: 'connected',
    peerCount: 3,
    lastSyncTime: Date.now(),
    secondsSinceSync: 2,
  };

  it('should show green dot and peer count when connected', () => {
    render(<ConnectionStatus connectionInfo={baseInfo} />);
    expect(screen.getByText('3 peers')).toBeInTheDocument();
  });

  it('should show 0 peers label when peerCount is 0', () => {
    render(
      <ConnectionStatus connectionInfo={{ ...baseInfo, peerCount: 0 }} />,
    );
    expect(screen.getByText('0 peers')).toBeInTheDocument();
  });

  it('should show 1 peer label when peerCount is 1', () => {
    render(
      <ConnectionStatus connectionInfo={{ ...baseInfo, peerCount: 1 }} />,
    );
    expect(screen.getByText('1 peers')).toBeInTheDocument();
  });

  it('should show tooltip with full status on hover', async () => {
    render(<ConnectionStatus connectionInfo={baseInfo} />);
    // Hover over the indicator
    const container = screen.getByText('3 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    // Tooltip should show "Connected" and "Synced just now". Regex tolerates
    // identity-marker ZWJ/ZWNJ trailing the visible text.
    expect(screen.getByText(/Connected/)).toBeInTheDocument();
    expect(screen.getByText(/Synced.*just now/)).toBeInTheDocument();
  });

  it('should show "Connecting..." for connecting state', () => {
    render(
      <ConnectionStatus
        connectionInfo={{ ...baseInfo, status: 'connecting', peerCount: 0 }}
      />,
    );
    const container = screen.getByText('0 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    expect(screen.getByText(/Connecting/)).toBeInTheDocument();
  });

  it('should show "Disconnected" for disconnected state', () => {
    render(
      <ConnectionStatus
        connectionInfo={{
          ...baseInfo,
          status: 'disconnected',
          peerCount: 0,
          lastSyncTime: null,
          secondsSinceSync: null,
        }}
      />,
    );
    const container = screen.getByText('0 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    expect(screen.getByText(/Disconnected/)).toBeInTheDocument();
  });

  it('should show seconds-ago sync label for older syncs', () => {
    render(
      <ConnectionStatus
        connectionInfo={{ ...baseInfo, secondsSinceSync: 30 }}
      />,
    );
    const container = screen.getByText('3 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    expect(screen.getByText(/Synced.*30s.*ago/)).toBeInTheDocument();
  });

  it('should show minutes-ago sync label for much older syncs', () => {
    render(
      <ConnectionStatus
        connectionInfo={{ ...baseInfo, secondsSinceSync: 120 }}
      />,
    );
    const container = screen.getByText('3 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    expect(screen.getByText(/Synced.*2m.*ago/)).toBeInTheDocument();
  });

  it('should hide tooltip on mouse leave', () => {
    vi.useFakeTimers();
    render(<ConnectionStatus connectionInfo={baseInfo} />);
    const container = screen.getByText('3 peers').closest('div')!;
    fireEvent.mouseEnter(container);
    expect(screen.getByText(/Connected/)).toBeInTheDocument();
    fireEvent.mouseLeave(container);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByText(/Connected/)).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});

// --- CollaborationBar integration tests ---

describe('CollaborationBar with ConnectionStatus', () => {
  const mockUsers: CollabUser[] = [
    { userId: '1', userName: 'Alice', color: '#3b82f6', cursor: null, isLocal: true },
    { userId: '2', userName: 'Bob', color: '#10b981', cursor: null, isLocal: false },
  ];

  const connInfo: ConnectionStatusInfo = {
    status: 'connected',
    peerCount: 1,
    lastSyncTime: Date.now(),
    secondsSinceSync: 3,
  };

  it('should render ConnectionStatus inside the bar when connectionInfo is provided', () => {
    render(
      <CollaborationBar users={mockUsers} connected={true} connectionInfo={connInfo} />,
    );
    expect(screen.getByText('1 peers')).toBeInTheDocument();
  });

  it('should fall back to legacy connected boolean when connectionInfo is not provided', () => {
    render(<CollaborationBar users={mockUsers} connected={true} />);
    // Fallback builds info from users: 1 remote user = 1 peer
    expect(screen.getByText('1 peers')).toBeInTheDocument();
  });

  it('should show disconnected state via fallback when connected=false', () => {
    render(<CollaborationBar users={[]} connected={false} />);
    // Fallback: status=disconnected, peerCount=0
    expect(screen.getByText('0 peers')).toBeInTheDocument();
  });

  it('should still show user avatars alongside the connection indicator', () => {
    render(
      <CollaborationBar users={mockUsers} connected={true} connectionInfo={connInfo} />,
    );
    // Users count label ("2 online") — text is split across nodes (count +
    // i18n suffix), so use a node-content matcher and tolerate ZW chars.
    expect(
      screen.getByText((_content, el) => {
        const txt = el?.textContent?.replace(/[-]/g, '') ?? '';
        return txt === '2 online';
      }),
    ).toBeInTheDocument();
  });
});
