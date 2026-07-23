// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import { ProjectWeather } from '@/shared/ui/ProjectWeather/ProjectWeather';
import { resolveProjectCoords, type ProjectPin } from './DashboardProjectsMap';

interface DashboardSitesPanelProps {
  projects: ProjectPin[];
}

interface SiteRow {
  id: string;
  name: string;
  cityLabel: string;
  coords: { lat: number; lng: number } | null;
}

/**
 * Right-side companion to the dashboard project map. Shows up to six of the
 * project cities in a tidy 2-column grid (three rows, no inner scrollbar),
 * each cell carrying a compact Open-Meteo weather summary (next 7 days and
 * ~15-day average) so a manager can spot bad weather coming to a site at a
 * glance. Cells link to the first project in that city.
 *
 * Coordinates come from the shared `resolveProjectCoords` helper (explicit
 * lat/lng, then the geocode cache the map fills, then a region centroid),
 * so weather appears without waiting on the map's async geocoder.
 */
export function DashboardSitesPanel({ projects }: DashboardSitesPanelProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const groups = useMemo(() => {
    const otherLabel = t('dashboard.sites_other', { defaultValue: 'Other locations' });
    const rows: SiteRow[] = projects.map((p) => ({
      id: p.id,
      name: p.name,
      cityLabel: (p.city || p.country || p.region || '').trim(),
      coords: resolveProjectCoords(p),
    }));
    const byCity = new Map<string, SiteRow[]>();
    for (const r of rows) {
      const key = r.cityLabel || otherLabel;
      const bucket = byCity.get(key);
      if (bucket) bucket.push(r);
      else byCity.set(key, [r]);
    }
    // Named cities alphabetically, the unlabeled bucket last.
    return [...byCity.entries()].sort((a, b) => {
      if (a[0] === otherLabel) return 1;
      if (b[0] === otherLabel) return -1;
      return a[0].localeCompare(b[0]);
    });
  }, [projects, t]);

  // Exactly six city cells fill a 3-row, 2-column grid. If more cities exist
  // we simply show the first six and drop the scrollbar entirely.
  const cities = groups.slice(0, 6);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border-light bg-surface-elevated/90">
      <div className="flex items-center justify-between border-b border-border-light px-3 py-2">
        <span className="text-xs font-semibold text-content-primary">
          {t('dashboard.sites_title', { defaultValue: 'Sites & weather' })}
        </span>
        <span className="text-[10px] tabular-nums text-content-tertiary">{groups.length}</span>
      </div>
      <div className="grid flex-1 auto-rows-fr grid-cols-2 gap-2 overflow-hidden p-2">
        {cities.map(([city, rows]) => {
          const lead = rows[0];
          const coords = lead?.coords ?? null;
          return (
            <button
              key={city}
              type="button"
              onClick={() => {
                if (lead) navigate(`/projects/${lead.id}`);
              }}
              className="group flex min-w-0 flex-col justify-center gap-1 rounded-lg border border-border-light bg-surface-primary/50 px-2.5 py-2 text-left transition-colors hover:border-oe-blue/40 hover:bg-surface-primary"
            >
              <span className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue">
                  <MapPin size={11} />
                </span>
                <span className="truncate text-xs font-semibold text-content-primary">{city}</span>
                {rows.length > 1 && (
                  <span className="shrink-0 text-[10px] tabular-nums text-content-tertiary">
                    {rows.length}
                  </span>
                )}
              </span>
              {coords ? (
                <ProjectWeather
                  lat={coords.lat}
                  lng={coords.lng}
                  locale={i18n.language}
                  variant="summary"
                  className="pl-6"
                />
              ) : (
                <span className="pl-6 text-[10px] text-content-quaternary">
                  {t('dashboard.sites_no_location', { defaultValue: 'No location set' })}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
