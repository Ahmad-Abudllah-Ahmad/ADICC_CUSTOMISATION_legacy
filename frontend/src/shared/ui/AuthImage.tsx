// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useEffect, useState } from 'react';
import type { ImgHTMLAttributes, ReactNode } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';

export interface AuthImageProps
  extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  /** API URL of the JWT-protected image (photo thumb / original / etc). */
  src: string;
  /** Rendered while the blob is being fetched. */
  placeholder?: ReactNode;
  /** Rendered when the fetch fails (401, 404, network). */
  fallback?: ReactNode;
}

/**
 * <img> for endpoints that require an `Authorization: Bearer` header.
 *
 * A plain `<img src>` request never carries the JWT, so auth-protected
 * media 401s. This fetches the resource with the bearer token, turns it
 * into an object URL, and revokes it on unmount / src change so blobs
 * are not leaked.
 */
export function AuthImage({
  src,
  placeholder = null,
  fallback = null,
  ...imgProps
}: AuthImageProps) {
  const [objUrl, setObjUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    setObjUrl(null);
    setFailed(false);

    const token = useAuthStore.getState().accessToken;
    const headers: HeadersInit = { Accept: 'image/*' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    fetch(src, { headers })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setObjUrl(created);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [src]);

  if (failed) return <>{fallback}</>;
  if (!objUrl) return <>{placeholder}</>;
  // A11y: every <img> needs an alt attribute. Callers that pass `alt`
  // win via {...imgProps}; we fall back to an empty alt (decorative)
  // so the rendered <img> always has the attribute present.
  return <img alt="" {...imgProps} src={objUrl} />;
}
