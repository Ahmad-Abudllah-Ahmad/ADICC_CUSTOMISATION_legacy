// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useState } from 'react';
import clsx from 'clsx';
import { RoleAvatar } from './RoleAvatar';
import type { ProfessionalRole } from './types';

interface RoleArtProps {
  role: ProfessionalRole;
  /** Sizing classes (height + width). Rendered as a circular tile. */
  className?: string;
  title?: string;
}

/**
 * The line-art portrait for a professional role, in a circular always-light tile
 * so the slate linework reads in both themes. Falls back to the drawn SVG persona
 * ({@link RoleAvatar}) if the picture is missing.
 */
export function RoleArt({ role, className, title }: RoleArtProps) {
  const [broken, setBroken] = useState(false);
  const [lastRole, setLastRole] = useState(role);
  // Reset the fallback during render when reused for another role (the persona
  // strip swaps role in place), so the portrait never flashes the old avatar.
  if (role !== lastRole) {
    setLastRole(role);
    setBroken(false);
  }

  if (broken) {
    return <RoleAvatar role={role} className={className} title={title} />;
  }

  return (
    <span
      title={title}
      className={clsx(
        'inline-flex shrink-0 overflow-hidden rounded-full bg-white ring-1 ring-inset ring-border-light dark:bg-slate-100',
        className,
      )}
    >
      <img
        src={`/cases-art/roles/${role}.webp`}
        alt=""
        loading="lazy"
        decoding="async"
        width={384}
        height={384}
        draggable={false}
        onError={() => setBroken(true)}
        className="h-full w-full object-cover"
      />
    </span>
  );
}
