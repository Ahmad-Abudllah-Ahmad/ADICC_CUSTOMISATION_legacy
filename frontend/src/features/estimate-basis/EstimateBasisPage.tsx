// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
/**
 * Basis of Estimate - standalone page host.
 *
 * The estimate-basis feature ships its working surface as an embeddable
 * `EstimateBasisPanel` (project + BOQ scoped). This thin page wires it to the
 * active project context so it is reachable as its own route, matching how the
 * other project-scoped estimating tools are mounted.
 */

import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { EstimateBasisPanel } from './EstimateBasisPanel';
import { HowBasisWorks } from './HowBasisWorks';

export function EstimateBasisPage() {
  const { t } = useTranslation();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const activeBOQId = useProjectContextStore((s) => s.activeBOQId);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        srTitle={t('estimate_basis.title', { defaultValue: 'Basis of Estimate' })}
        subtitle={t('estimate_basis.subtitle', {
          defaultValue:
            'Draft the inclusions, exclusions, assumptions and pricing basis behind the estimate, so a reviewer can see what the number does and does not cover.',
        })}
      />
      <HowBasisWorks />
      {activeProjectId ? (
        <EstimateBasisPanel projectId={activeProjectId} boqId={activeBOQId} />
      ) : (
        <RequiresProject>{null}</RequiresProject>
      )}
    </div>
  );
}
