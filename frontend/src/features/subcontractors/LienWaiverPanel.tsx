// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Lien waivers / tax forms panel — list + upload dialog.
 *
 * Renders inside the DetailDrawer below the existing Certificates
 * summary. Uploads go to
 *   POST /api/v1/subcontractors/subcontractors/{id}/lien-waivers/upload
 * which gates the file against the document magic-byte allow-list
 * (pdf, png, jpeg, gif, webp). The server returns 415 for any other
 * format and we render that as a Toast.
 *
 * Free-standing W-9 / W-8 tax forms are stored alongside per-draw
 * waivers; the difference is purely the ``waiver_type`` enum.
 */

import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Upload, FileSignature, Trash2, Loader2 } from 'lucide-react';
import {
  Badge,
  Button,
  EmptyState,
  SkeletonTable,
} from '@/shared/ui';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { apiGet, apiDelete, getErrorMessage, getAuthToken, API_BASE } from '@/shared/lib/api';

// Six values to match the backend ``_VALID_WAIVER_TYPES`` enum. Keep
// labels short (table-row friendly); ``defaultValue`` covers the
// untranslated case.
const WAIVER_TYPES: Array<{ value: string; label: string }> = [
  { value: 'conditional_partial', label: 'Conditional · Partial' },
  { value: 'conditional_final', label: 'Conditional · Final' },
  { value: 'unconditional_partial', label: 'Unconditional · Partial' },
  { value: 'unconditional_final', label: 'Unconditional · Final' },
  { value: 'w9', label: 'W-9 (US tax)' },
  { value: 'w8', label: 'W-8 (Intl tax)' },
];

// MIME allow-list shown in the <input accept=…> attribute. The server
// still re-validates by magic bytes — this is a UX nudge only.
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.gif,.webp,application/pdf,image/*';

interface LienWaiver {
  id: string;
  waiver_type: string;
  document_url: string;
  mime_type: string | null;
  file_size: number | null;
  signed_date: string | null;
  amount: number | string;
  currency: string;
  notes: string | null;
  created_at: string;
}

interface LienWaiverPanelProps {
  subcontractorId: string;
}

export function LienWaiverPanel({ subcontractorId }: LienWaiverPanelProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadType, setUploadType] = useState<string>('conditional_partial');
  const [busy, setBusy] = useState(false);

  const listQ = useQuery({
    queryKey: ['subcontractors', 'lien-waivers', subcontractorId],
    queryFn: () =>
      apiGet<LienWaiver[]>(
        `/v1/subcontractors/subcontractors/${subcontractorId}/lien-waivers`,
      ),
    enabled: !!subcontractorId,
  });

  /**
   * POST a multipart form to /lien-waivers/upload. Native fetch is used
   * (not `apiPost`) because the helper only supports JSON bodies; we
   * still pull the bearer token via getAuthToken so the request lands
   * authenticated and the request ID middleware threads through.
   */
  const handleFile = async (file: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append('waiver_type', uploadType);
      form.append('file', file);
      const token = getAuthToken();
      const resp = await fetch(
        `${API_BASE}/v1/subcontractors/subcontractors/${subcontractorId}/lien-waivers/upload`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: form,
        },
      );
      if (!resp.ok) {
        // 415 → format rejected. 413 → too big. 422 → bad waiver_type
        // / corrupt amount. Surface the server's detail verbatim
        // because it's already user-friendly.
        let detail: string;
        try {
          const j = await resp.json();
          detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j);
        } catch {
          detail = `HTTP ${resp.status}`;
        }
        addToast({
          type: 'error',
          title: t('subcontractors.upload_failed', {
            defaultValue: 'Upload failed',
          }),
          message: detail,
        });
        return;
      }
      addToast({
        type: 'success',
        title: t('subcontractors.waiver_uploaded', {
          defaultValue: 'Lien waiver uploaded',
        }),
      });
      qc.invalidateQueries({
        queryKey: ['subcontractors', 'lien-waivers', subcontractorId],
      });
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (waiverId: string) => {
    try {
      await apiDelete(
        `/v1/subcontractors/subcontractors/${subcontractorId}/lien-waivers/${waiverId}`,
      );
      addToast({
        type: 'success',
        title: t('subcontractors.waiver_deleted', {
          defaultValue: 'Lien waiver removed',
        }),
      });
      qc.invalidateQueries({
        queryKey: ['subcontractors', 'lien-waivers', subcontractorId],
      });
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    }
  };

  const rows = listQ.data ?? [];

  return (
    <section
      aria-label={t('subcontractors.lien_waivers_aria', {
        defaultValue: 'Lien waivers and tax forms',
      })}
      className="space-y-2"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-content-secondary">
          {t('subcontractors.lien_waivers_title', {
            defaultValue: 'Lien waivers & tax forms',
          })}
        </h3>
        <div className="flex items-center gap-1.5">
          <select
            value={uploadType}
            onChange={(e) => setUploadType(e.target.value)}
            className="h-8 rounded-md border border-border-light bg-surface-primary px-2 text-xs"
            aria-label={t('subcontractors.lien_waiver_type', {
              defaultValue: 'Waiver type',
            })}
            disabled={busy}
          >
            {WAIVER_TYPES.map((w) => (
              <option key={w.value} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
            aria-label={t('subcontractors.lien_waiver_file_input', {
              defaultValue: 'Lien waiver file',
            })}
          />
          <Button
            variant="secondary"
            size="sm"
            icon={busy ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
          >
            {t('subcontractors.upload_waiver', { defaultValue: 'Upload' })}
          </Button>
        </div>
      </div>

      {listQ.isLoading && <SkeletonTable rows={2} columns={4} />}

      {!listQ.isLoading && rows.length === 0 && (
        <EmptyState
          icon={<FileSignature size={18} />}
          title={t('subcontractors.no_lien_waivers', {
            defaultValue: 'No lien waivers yet',
          })}
          description={t('subcontractors.no_lien_waivers_desc', {
            defaultValue:
              'Upload signed lien waivers (PDF / image) and W-9 / W-8 tax forms here. Server validates file content by magic bytes.',
          })}
        />
      )}

      {!listQ.isLoading && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border-light">
          <table className="w-full text-xs">
            <thead className="bg-surface-secondary text-content-tertiary uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left">
                  {t('subcontractors.waiver_type_col', { defaultValue: 'Type' })}
                </th>
                <th className="px-3 py-2 text-left">
                  {t('subcontractors.signed_date_col', { defaultValue: 'Signed' })}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('subcontractors.amount', { defaultValue: 'Amount' })}
                </th>
                <th className="px-3 py-2 text-left">
                  {t('subcontractors.uploaded', { defaultValue: 'Uploaded' })}
                </th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.id} className="border-t border-border-light">
                  <td className="px-3 py-2">
                    <Badge variant="blue" size="sm">
                      {WAIVER_TYPES.find((wt) => wt.value === w.waiver_type)?.label ||
                        w.waiver_type}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-content-secondary">
                    {w.signed_date || '—'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {typeof w.amount === 'string' ? w.amount : w.amount.toFixed(2)}{' '}
                    <span className="text-content-tertiary">{w.currency || ''}</span>
                  </td>
                  <td className="px-3 py-2 text-content-secondary">
                    <DateDisplay value={w.created_at} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => handleDelete(w.id)}
                      className={clsx(
                        'inline-flex items-center justify-center rounded p-1 text-content-tertiary',
                        'hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/30',
                      )}
                      aria-label={t('subcontractors.delete_waiver', {
                        defaultValue: 'Delete lien waiver',
                      })}
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
