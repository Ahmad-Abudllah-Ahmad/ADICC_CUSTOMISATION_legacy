// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useEffect, useRef, useState } from 'react';
import * as Y from 'yjs';
import { WebrtcProvider } from 'y-webrtc';
import { WebsocketProvider } from 'y-websocket';

export type ProviderType = WebrtcProvider | WebsocketProvider;

export interface UseYDocResult {
  doc: Y.Doc | null;
  provider: ProviderType | null;
  connected: boolean;
  /** Which provider type is currently active */
  providerKind: 'webrtc' | 'websocket' | null;
}

// Real-time collaboration is OFF by default and never talks to a public
// relay. BOQ document edits can carry confidential project pricing, so we
// refuse to broadcast them through third-party servers (the y-webrtc /
// y-websocket demo infrastructure at signaling.yjs.dev / demos.yjs.dev).
// An operator who wants live multi-user editing points these at their OWN
// self-hosted relay via build-time env vars (VITE_COLLAB_*) or a per-browser
// localStorage override. With nothing configured the Y.Doc still works fully
// for a single user; it just stays local and no document data leaves the tab.
const WS_URL_KEY = 'oe_collab_ws_url';
const SIGNALING_KEY = 'oe_collab_signaling';

function getWsUrl(): string {
  const fromEnv = (import.meta.env.VITE_COLLAB_WS_URL as string | undefined)?.trim();
  if (fromEnv) return fromEnv;
  try {
    return (localStorage.getItem(WS_URL_KEY) ?? '').trim();
  } catch {
    return '';
  }
}

/** Self-hosted WebRTC signaling servers, or [] to keep collaboration local.
 *  Returning [] (rather than omitting the option) is what stops y-webrtc from
 *  falling back to its built-in public signaling servers. */
function getSignaling(): string[] {
  const parse = (raw: string | undefined | null): string[] =>
    (raw ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  const fromEnv = parse(import.meta.env.VITE_COLLAB_SIGNALING as string | undefined);
  if (fromEnv.length > 0) return fromEnv;
  try {
    return parse(localStorage.getItem(SIGNALING_KEY));
  } catch {
    return [];
  }
}

/**
 * Initialize a Yjs document with WebRTC provider.
 * Falls back to WebSocket if WebRTC fails to connect within 8 seconds.
 * Room name = `boq:{boqId}`.
 */
export function useYDoc(boqId: string | undefined): UseYDocResult {
  const [connected, setConnected] = useState(false);
  const [providerKind, setProviderKind] = useState<'webrtc' | 'websocket' | null>(null);
  const docRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<ProviderType | null>(null);

  useEffect(() => {
    if (!boqId) return;

    const doc = new Y.Doc();
    const roomName = `boq:${boqId}`;
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined;
    let wsProvider: WebsocketProvider | null = null;

    // Start with WebRTC. Pass the operator's signaling servers, or [] to keep
    // the session local (an empty list disables peer discovery entirely, so no
    // document data is ever relayed through a public server).
    const rtcProvider = new WebrtcProvider(roomName, doc, {
      signaling: getSignaling(),
    });

    const onRtcSynced = () => {
      setConnected(true);
      setProviderKind('webrtc');
      if (fallbackTimer) clearTimeout(fallbackTimer);
    };

    rtcProvider.on('synced', onRtcSynced);
    rtcProvider.on('status', (event: { connected: boolean }) => {
      if (event.connected) {
        setConnected(true);
        setProviderKind('webrtc');
        if (fallbackTimer) clearTimeout(fallbackTimer);
      }
    });

    docRef.current = doc;
    providerRef.current = rtcProvider;
    setProviderKind('webrtc');

    // Fallback: if WebRTC doesn't connect within 8s, add a WebSocket provider,
    // but ONLY when the operator has configured their own relay URL. With no
    // URL set we stay local instead of dialing a public demo server.
    fallbackTimer = setTimeout(() => {
      if (connected) return; // Already connected via WebRTC
      const wsUrl = getWsUrl();
      if (!wsUrl) return; // No self-hosted relay configured: stay local.
      try {
        wsProvider = new WebsocketProvider(wsUrl, roomName, doc);
        wsProvider.on('status', (event: { status: string }) => {
          if (event.status === 'connected') {
            setConnected(true);
            setProviderKind('websocket');
            providerRef.current = wsProvider;
          }
        });
      } catch {
        // WebSocket fallback failed — stay with WebRTC attempt
      }
    }, 8000);

    return () => {
      if (fallbackTimer) clearTimeout(fallbackTimer);
      rtcProvider.disconnect();
      rtcProvider.destroy();
      if (wsProvider) {
        wsProvider.disconnect();
        wsProvider.destroy();
      }
      doc.destroy();
      docRef.current = null;
      providerRef.current = null;
      setConnected(false);
      setProviderKind(null);
    };
  }, [boqId]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    doc: docRef.current,
    provider: providerRef.current,
    connected,
    providerKind,
  };
}
