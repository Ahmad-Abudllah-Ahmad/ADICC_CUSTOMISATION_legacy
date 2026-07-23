// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** RevisionsPanel — Epic C unified revisions list.
 *
 *  Larger sibling of ``VersionDropdown``: rendered inside the file
 *  preview pane (right-hand drawer) when the user opens "Revisions".
 *  Shows the full chain newest-first with:
 *
 *    * a "current" pill on the active row;
 *    * the upload timestamp + notes;
 *    * a "Restore" action on historical rows;
 *    * an "Upload new revision" CTA at the top.
 *
 *  This component does NOT itself handle the upload — that's wired in
 *  the parent via the ``onUploadNew`` callback (so the wider preview
 *  pane can mount the file-picker / progress UI it already owns).
 */

import { useTranslation } from 'react-i18next';
import { Loader2, RotateCcw, Upload } from 'lucide-react';
import clsx from 'clsx';
import { useToastStore } from '@/stores/useToastStore';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useFileVersions, useRestoreVersion } from './hooks';
import { VersionBadge } from './VersionBadge';
import type { FileKind, FileVersionResponse } from './types';

interface RevisionsPanelProps {
  fileId: string;
  kind: FileKind;
  /** Only documents support "upload new revision" today — other kinds
   *  hide the CTA. */
  canUploadNewRevision?: boolean;
  onUploadNew?: () => void;
  /** Fires after a successful restore so the preview pane can refresh
   *  the rendered file. */
  onRestored?: (versionId: string) => void;
  className?: string;
}

function formatVersionLabel(n: number): string {
  return n < 100 ? `V${String(n).padStart(2, '0')}` : `V${n}`;
}

export function RevisionsPanel({
  fileId,
  kind,
  canUploadNewRevision = false,
  onUploadNew,
  onRestored,
  className,
}: RevisionsPanelProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const { data: versions, isLoading, isError } = useFileVersions(fileId, kind);
  const restore = useRestoreVersion(fileId, kind);

  const handleRestore = (row: FileVersionResponse) => {
    if (restore.isPending) return;
    restore.mutate(row.id, {
      onSuccess: (restored) => {
        addToast({
          type: 'success',
          title: t('files.versions.restored_title', {
            defaultValue: 'Restored to {{n}}',
            n: formatVersionLabel(restored.version_number),
          }),
        });
        onRestored?.(restored.id);
      },
      onError: (err: Error) => {
        addToast({
          type: 'error',
          title: t('files.versions.restore_failed', {
            defaultValue: 'Could not restore version',
          }),
          message: err.message,
        });
      },
    });
  };

  return (
    <section
      data-testid="revisions-panel"
      className={clsx('flex flex-col gap-3 p-4', className)}
      aria-label={t('files.versions.panel_aria', { defaultValue: 'Revisions panel' })}
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-content-primary">
          {t('files.versions.panel_title', { defaultValue: 'Revisions' })}
          {versions && versions.length > 0 && (
            <span className="ml-1 text-xs font-normal text-content-tertiary tabular-nums">
              ({versions.length})
            </span>
          )}
        </h3>
        {canUploadNewRevision && (
          <button
            type="button"
            onClick={() => onUploadNew?.()}
            data-testid="revisions-upload-new"
            className={clsx(
              'inline-flex items-center gap-1.5 h-7 px-2 rounded-md',
              'text-xs font-medium border border-border-light',
              'text-content-secondary hover:bg-surface-secondary',
            )}
          >
            <Upload size={12} />
            {t('files.versions.upload_new', { defaultValue: 'Upload new revision' })}
          </button>
        )}
      </header>

      {isLoading && (
        <div className="flex items-center gap-2 text-xs text-content-secondary">
          <Loader2 size={12} className="animate-spin" />
          {t('files.versions.loading', { defaultValue: 'Loading revisions…' })}
        </div>
      )}

      {isError && (
        <div
          role="alert"
          className="text-xs text-semantic-error"
        >
          {t('files.versions.load_failed', { defaultValue: 'Versions unavailable' })}
        </div>
      )}

      {!isLoading && !isError && versions && versions.length === 0 && (
        <p className="text-xs text-content-tertiary">
          {t('files.versions.empty', {
            defaultValue: 'No revisions yet. Re-uploads of this file will appear here.',
          })}
        </p>
      )}

      {versions && versions.length > 0 && (
        <ol
          className="flex flex-col divide-y divide-border-light rounded-lg border border-border-light bg-surface-elevated"
          data-testid="revisions-list"
        >
          {versions.map((v) => (
            <li
              key={v.id}
              data-testid={`revisions-row-${v.version_number}`}
              className="flex items-start gap-3 px-3 py-2 text-xs"
            >
              <VersionBadge versionNumber={v.version_number} isCurrent={v.is_current} />
              <div className="flex-1 min-w-0">
                <DateDisplay
                  value={v.uploaded_at}
                  format="datetime"
                  className="text-[10px] text-content-tertiary"
                />
                {v.notes && (
                  <p className="mt-1 text-[11px] text-content-secondary line-clamp-3">
                    {v.notes}
                  </p>
                )}
              </div>
              {!v.is_current && (
                <button
                  type="button"
                  onClick={() => handleRestore(v)}
                  disabled={restore.isPending}
                  data-testid={`revisions-restore-${v.version_number}`}
                  className={clsx(
                    'inline-flex items-center gap-1 h-6 px-1.5 rounded text-[10px] font-medium',
                    'text-oe-blue hover:bg-oe-blue/10',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                  title={t('files.versions.make_current_title', {
                    defaultValue: 'Promote this version to current',
                  })}
                >
                  {restore.isPending ? (
                    <Loader2 size={10} className="animate-spin" />
                  ) : (
                    <RotateCcw size={10} />
                  )}
                  {t('files.versions.make_current', { defaultValue: 'Make current' })}
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
