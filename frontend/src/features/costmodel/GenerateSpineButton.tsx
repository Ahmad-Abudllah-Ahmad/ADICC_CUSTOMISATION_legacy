// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// GenerateSpineButton - kicks off "generate cost spine from BOQ" and reports
// the created counts via a toast, then invalidates the spine query so the
// panel re-fetches the freshly built tree.

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Network } from 'lucide-react';

import { Button } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import { costModelApi, type SpineGenerationResult } from './api';

export interface GenerateSpineButtonProps {
  projectId: string;
  /** Optional BOQ to generate from; omit to let the backend pick the default. */
  boqId?: string;
  /** Visual size passed through to the shared Button. */
  size?: 'sm' | 'md';
  /** Visual variant passed through to the shared Button. */
  variant?: 'primary' | 'secondary';
}

/**
 * Button that generates the cost spine from a BOQ.
 *
 * On success it shows a toast naming how many control accounts and cost lines
 * were created, then invalidates the ``['spine', projectId]`` query so the
 * spine panel refreshes. On failure it surfaces the error in a toast.
 */
export function GenerateSpineButton({
  projectId,
  boqId,
  size = 'sm',
  variant = 'secondary',
}: GenerateSpineButtonProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const generate = useMutation({
    mutationFn: () => costModelApi.generateSpine(projectId, boqId),
    onSuccess: (result: SpineGenerationResult) => {
      addToast({
        type: 'success',
        title: t('costmodel.spine.generated_title', { defaultValue: 'Cost spine generated' }),
        message: t('costmodel.spine.generated_counts', {
          defaultValue: '{{accounts}} control accounts and {{lines}} cost lines created.',
          accounts: result?.accounts_created ?? 0,
          lines: result?.lines_created ?? 0,
        }),
      });
      queryClient.invalidateQueries({ queryKey: ['spine', projectId] });
    },
    onError: (err: unknown) => {
      addToast({
        type: 'error',
        title: t('costmodel.spine.generate_failed', { defaultValue: 'Failed to generate cost spine' }),
        message: getErrorMessage(err),
      });
    },
  });

  const handleClick = useCallback(() => {
    generate.mutate();
  }, [generate]);

  return (
    <Button
      variant={variant}
      size={size}
      icon={<Network size={size === 'sm' ? 14 : 16} />}
      loading={generate.isPending}
      onClick={handleClick}
    >
      {t('costmodel.spine.generate_cta', { defaultValue: 'Generate from BOQ' })}
    </Button>
  );
}
