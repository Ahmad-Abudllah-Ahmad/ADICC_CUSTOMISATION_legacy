// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';

import type { BIMElementData } from './ElementManager';
import { buildElementQuestion } from './elementQuestion';

/** Minimal element: only the two always-present fields. */
function bare(overrides: Partial<BIMElementData> = {}): BIMElementData {
  return {
    id: 'e1',
    name: '',
    element_type: 'Wall',
    discipline: '',
    ...overrides,
  };
}

describe('buildElementQuestion', () => {
  it('produces a usable prompt for a bare element and never throws', () => {
    const out = buildElementQuestion(bare());
    expect(out).toContain('Element: Wall');
    // Always ends with the closing question so the user can send as-is.
    expect(out).toMatch(/Please summarise/);
    expect(out.length).toBeGreaterThan(0);
  });

  it('falls back to element_type when name is blank', () => {
    expect(buildElementQuestion(bare({ name: '   ' }))).toContain('Element: Wall');
  });

  it('prefers the human name when present, with discipline and storey', () => {
    const out = buildElementQuestion(
      bare({ name: 'North wall', discipline: 'structural', storey: 'L2' }),
    );
    expect(out).toContain('Element: North wall (Wall, structural, storey L2)');
  });

  it('coerces Decimal-string money into a readable cost line', () => {
    // Money arrives as strings over the wire even though the type says number.
    const el = bare({
      boq_links: [
        {
          id: 'l1',
          boq_position_id: 'p1',
          boq_position_ordinal: '01.001',
          boq_position_description: 'RC slab',
          boq_position_quantity: '10' as unknown as number,
          boq_position_unit: 'm3',
          boq_position_unit_rate: '185' as unknown as number,
          boq_position_total: '1850' as unknown as number,
          link_type: 'manual',
          confidence: null,
        },
      ],
    });
    const out = buildElementQuestion(el);
    expect(out).toContain('Linked BOQ: 01.001 RC slab - 10 m3 @ 185 = 1,850');
  });

  it('lists documents, tasks, schedule and requirements when present', () => {
    const out = buildElementQuestion(
      bare({
        linked_documents: [
          {
            id: 'd1',
            document_id: 'doc1',
            document_name: 'A-201',
            document_category: 'drawing',
            link_type: 'manual',
            confidence: null,
          },
        ],
        linked_tasks: [
          {
            id: 't1',
            project_id: 'pr1',
            title: 'Pour slab',
            status: 'in_progress',
            task_type: null,
            due_date: null,
          },
        ],
        linked_activities: [
          {
            id: 'a1',
            name: 'Concrete L2',
            start_date: null,
            end_date: null,
            status: 'active',
            percent_complete: 40,
          },
        ],
        linked_requirements: [
          {
            id: 'r1',
            requirement_set_id: 's1',
            entity: 'Slab',
            attribute: 'fire_rating',
            constraint_type: '=',
            constraint_value: 'F90',
            unit: '',
            category: 'fire',
            priority: 'must',
            status: 'open',
          },
        ],
      }),
    );
    expect(out).toContain('Linked documents: A-201');
    expect(out).toContain('Linked tasks: Pour slab (in_progress)');
    expect(out).toContain('Schedule: Concrete L2 (active, 40%)');
    expect(out).toContain('Requirements: Slab fire_rating = F90 [open]');
  });

  it('omits validation when unchecked and includes it otherwise', () => {
    expect(buildElementQuestion(bare({ validation_status: 'unchecked' }))).not.toContain(
      'Validation:',
    );
    const warned = buildElementQuestion(
      bare({
        validation_status: 'warning',
        validation_results: [
          { rule_id: 'boq.qty', severity: 'warning', message: 'Missing quantity' },
        ],
      }),
    );
    expect(warned).toContain('Validation: warning - warning: Missing quantity');
  });

  it('stays under the assistant input cap even with many links', () => {
    const many = Array.from({ length: 50 }, (_, i) => ({
      id: `l${i}`,
      boq_position_id: `p${i}`,
      boq_position_ordinal: `01.${i}`,
      boq_position_description: 'A very long BOQ position description repeated many times over',
      boq_position_quantity: 1,
      boq_position_unit: 'm3',
      boq_position_unit_rate: 100,
      boq_position_total: 100,
      link_type: 'manual' as const,
      confidence: null,
    }));
    const out = buildElementQuestion(bare({ boq_links: many }));
    expect(out.length).toBeLessThanOrEqual(4510);
  });

  it('does not emit em or en dashes', () => {
    const out = buildElementQuestion(
      bare({
        name: 'North wall',
        boq_links: [
          {
            id: 'l1',
            boq_position_id: 'p1',
            boq_position_ordinal: '01.001',
            boq_position_description: 'RC slab',
            boq_position_quantity: 10,
            boq_position_unit: 'm3',
            boq_position_unit_rate: 185,
            boq_position_total: 1850,
            link_type: 'manual',
            confidence: null,
          },
        ],
      }),
    );
    expect(out).not.toMatch(/[–—]/);
  });
});
