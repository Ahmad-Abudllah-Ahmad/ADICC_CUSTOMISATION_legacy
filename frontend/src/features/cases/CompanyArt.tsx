// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useState, type ComponentType } from 'react';
import clsx from 'clsx';
import type { LucideProps } from 'lucide-react';

/**
 * Company-type ids that have a generated line-art emblem at
 * /cases-art/company/<id>.webp. Add ids here as emblems are produced; until a
 * type is listed it renders its lucide glyph and no image request is attempted,
 * so the selector never fires a wasted 404.
 */
const COMPANY_ART_IDS = new Set<string>([]);

interface CompanyArtProps {
  /** Company-type id; maps to /cases-art/company/<id>.webp. */
  id: string;
  /** Glyph shown until (or if) an emblem picture exists for this type. */
  fallbackIcon: ComponentType<LucideProps>;
  /** Colour class for the fallback glyph. */
  fallbackClass?: string;
  className?: string;
  title?: string;
}

/**
 * The line-art emblem for a company type, in a rounded-square always-light tile.
 * Falls back to the type's lucide glyph (with no network request) for any type
 * that does not yet have an emblem, so the selector always renders something
 * distinguishable and fast.
 */
export function CompanyArt({
  id,
  fallbackIcon: Icon,
  fallbackClass,
  className,
  title,
}: CompanyArtProps) {
  const [broken, setBroken] = useState(false);
  const [lastId, setLastId] = useState(id);
  if (id !== lastId) {
    setLastId(id);
    setBroken(false);
  }

  if (broken || !COMPANY_ART_IDS.has(id)) {
    return (
      <span
        title={title}
        className={clsx(
          'inline-flex shrink-0 items-center justify-center rounded-xl bg-white ring-1 ring-inset ring-border-light dark:bg-slate-100',
          className,
        )}
      >
        <Icon size={26} strokeWidth={1.7} className={fallbackClass} aria-hidden="true" />
      </span>
    );
  }

  return (
    <span
      title={title}
      className={clsx(
        'inline-flex shrink-0 overflow-hidden rounded-xl bg-white ring-1 ring-inset ring-border-light dark:bg-slate-100',
        className,
      )}
    >
      <img
        src={`/cases-art/company/${id}.webp`}
        alt=""
        loading="lazy"
        decoding="async"
        width={384}
        height={384}
        draggable={false}
        onError={() => setBroken(true)}
        className="h-full w-full object-contain p-1.5"
      />
    </span>
  );
}
