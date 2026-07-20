// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import clsx from 'clsx';

interface LogoProps {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  animate?: boolean;
  className?: string;
}

/* Icon sizes — compact so the text dominates */
const sizeMap = {
  xs: 'h-5 w-5',
  sm: 'h-6 w-6',
  md: 'h-7 w-7',
  lg: 'h-10 w-10',
  xl: 'h-14 w-14',
};

/**
 * ADICC ERP brand mark — monogram "A" on a steel-blue gradient tile.
 */
export function Logo({ size = 'md', animate = false, className }: LogoProps) {
  const gradientId = `adicc-lg-${size}-${animate ? 'a' : 's'}`;

  const bgStyle = animate
    ? {
        animation: `oeBgScale 450ms cubic-bezier(0.34,1.56,0.64,1) both`,
      }
    : undefined;

  const letterStyle = animate
    ? {
        animation: `oeBuildingSlide 600ms cubic-bezier(0.22,1,0.36,1) both`,
        animationDelay: '180ms',
      }
    : undefined;

  return (
    <div
      className={clsx(sizeMap[size], 'relative shrink-0', className)}
      style={
        animate
          ? {
              animation:
                'oeLogoFloat 3s ease-in-out 1.2s infinite, oeLogoGlow 3s ease-in-out 1.2s infinite',
            }
          : undefined
      }
    >
      <svg viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0B4F6C" />
            <stop offset="100%" stopColor="#1B7A9A" />
          </linearGradient>
        </defs>

        <rect x="32" y="32" width="448" height="448" rx="96" fill={`url(#${gradientId})`} style={bgStyle} />

        {/* Stylized A */}
        <g style={letterStyle}>
          <path
            d="M256 118 L378 394 H318 L292 328 H220 L194 394 H134 L256 118 Z"
            fill="#fff"
            opacity="0.96"
          />
          <rect x="228" y="268" width="56" height="28" rx="4" fill={`url(#${gradientId})`} opacity="0.9" />
        </g>
      </svg>
    </div>
  );
}

/* ── LogoWithText ──────────────────────────────────────────────────────── */

interface LogoWithTextProps extends LogoProps {
  showVersion?: boolean;
}

/* Text sizes — larger than icon to make the name prominent */
const textSizeMap = {
  xs: 'text-[15px] leading-none',
  sm: 'text-[16px] leading-none',
  md: 'text-[17px] leading-none',
  lg: 'text-xl leading-none',
  xl: 'text-2xl leading-none',
};

const gapSizeMap = {
  xs: 'gap-1.5',
  sm: 'gap-2',
  md: 'gap-2',
  lg: 'gap-2.5',
  xl: 'gap-3',
};

/**
 * Logo + ADICC ERP wordmark.
 */
export function LogoWithText({ size = 'md', animate, showVersion = true, className }: LogoWithTextProps) {
  return (
    <div className={clsx('flex items-center', gapSizeMap[size], className)}>
      <Logo size={size} animate={animate} />
      <span
        className={clsx(
          textSizeMap[size],
          'font-medium text-content-primary whitespace-nowrap tracking-tight',
        )}
        style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", letterSpacing: '-0.02em' }}
      >
        ADICC
        {showVersion && <span className="text-content-quaternary"> ERP</span>}
      </span>
    </div>
  );
}
