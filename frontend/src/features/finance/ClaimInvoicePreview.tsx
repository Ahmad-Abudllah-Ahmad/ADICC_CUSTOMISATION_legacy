// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * ClaimInvoicePreview — Gap E (Wave 6).
 *
 * Shows the accounts-receivable invoice that a certified progress claim
 * spawns, with the retainage explicitly broken out (gross / retained / net
 * collectible). Lets a manager raise the receivable from the claim with one
 * click; the backend endpoint is idempotent, so a second click (or an
 * already-auto-created invoice from the certification event) simply re-shows
 * the existing invoice rather than duplicating it.
 *
 * Self-contained: drops into the contracts claim detail panel or the finance
 * page without touching either's large component. It only needs the claim id.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Card, CardContent, CardHeader } from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { apiGet, apiPost, getErrorMessage } from '@/shared/lib/api';

interface ClaimInvoiceLineItem {
  id: string;
  description: string;
  amount: string;
}

interface ClaimInvoice {
  id: string;
  invoice_number: string;
  status: string;
  currency_code: string;
  amount_subtotal: string;
  retention_amount: string;
  amount_total: string;
  source_claim_id: string | null;
  line_items?: ClaimInvoiceLineItem[];
}

export interface ClaimInvoicePreviewProps {
  /** The certified progress claim to preview / invoice. */
  claimId: string;
  /** Whether the current claim is in `certified` status (gates the action). */
  certified?: boolean;
  /** Called with the resulting invoice id after a successful raise. */
  onInvoiced?: (invoiceId: string) => void;
}

export function ClaimInvoicePreview({
  claimId,
  certified = true,
  onInvoiced,
}: ClaimInvoicePreviewProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  // Does an AR invoice already exist for this claim? 404 => not yet.
  const { data: existing, isLoading } = useQuery<ClaimInvoice | null>({
    queryKey: ['finance', 'claim-receivable', claimId],
    queryFn: async () => {
      try {
        return await apiGet<ClaimInvoice>(
          `/api/v1/finance/claims/${encodeURIComponent(claimId)}/receivable-invoice/`,
        );
      } catch {
        return null;
      }
    },
  });

  const raise = useMutation({
    mutationFn: async () => {
      return apiPost<ClaimInvoice>('/api/v1/finance/invoices/from-claim/', {
        claim_id: claimId,
      });
    },
    onSuccess: (inv) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ['finance', 'claim-receivable', claimId] });
      queryClient.invalidateQueries({ queryKey: ['finance', 'invoices'] });
      onInvoiced?.(inv.id);
    },
    onError: (e: unknown) => {
      setError(getErrorMessage(e));
    },
  });

  const invoice = existing ?? null;
  const currency = invoice?.currency_code || '';

  return (
    <Card>
      <CardHeader
        title={t('finance.claimInvoice.title')}
        action={
          invoice ? (
            <Badge variant="success">{t('finance.claimInvoice.raised')}</Badge>
          ) : (
            <Badge variant="neutral">{t('finance.claimInvoice.notRaised')}</Badge>
          )
        }
      />
      <CardContent>
        {isLoading ? (
          <p className="text-xs text-[var(--text-secondary)]">{t('common.loading')}</p>
        ) : invoice ? (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-[var(--text-secondary)]">
                {t('finance.claimInvoice.invoiceNumber')}
              </dt>
              <dd className="font-medium">{invoice.invoice_number}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--text-secondary)]">
                {t('finance.claimInvoice.gross')}
              </dt>
              <dd>
                <MoneyDisplay amount={invoice.amount_total} currency={currency} />
              </dd>
            </div>
            <div className="flex justify-between text-[var(--accent)]">
              <dt>{t('finance.claimInvoice.retained')}</dt>
              <dd>
                <MoneyDisplay amount={invoice.retention_amount} currency={currency} />
              </dd>
            </div>
            <div className="flex justify-between border-t border-[var(--border)] pt-2 font-semibold">
              <dt>{t('finance.claimInvoice.netCollectible')}</dt>
              <dd>
                <MoneyDisplay amount={invoice.amount_subtotal} currency={currency} />
              </dd>
            </div>
          </dl>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-[var(--text-secondary)]">
              {certified
                ? t('finance.claimInvoice.readyHint')
                : t('finance.claimInvoice.notCertifiedHint')}
            </p>
            <Button
              size="sm"
              onClick={() => raise.mutate()}
              disabled={!certified || raise.isPending}
            >
              {raise.isPending
                ? t('finance.claimInvoice.raising')
                : t('finance.claimInvoice.raiseAction')}
            </Button>
          </div>
        )}
        {error && <p className="mt-2 text-xs text-[var(--error)]">{error}</p>}
      </CardContent>
    </Card>
  );
}

export default ClaimInvoicePreview;
