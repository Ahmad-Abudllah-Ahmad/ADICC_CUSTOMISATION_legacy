// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get quantities from a BIM model".
//
// Import a converted model, read the element quantities, carry them into a bill
// and validate the result. No IfcOpenShell: the model arrives as canonical data
// through the converter. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "quantities-from-bim",
  order: 40,
  category: "bim",
  companyTypes: ["designer", "bim-consultant", "cost-consultant"],
  icon: "Box",
  titleKey: "cases.quantities_from_bim.title",
  titleDefault: "Get quantities from a BIM model",
  descKey: "cases.quantities_from_bim.desc",
  descDefault:
    "Load a converted model, lift the element quantities straight off the geometry, carry them into a priced bill and validate what you mapped.",
  estMinutes: 12,
  steps: [
    {
      id: "import",
      icon: "Box",
      inputs: [
        {
          labelKey: "cases.quantities_from_bim.step.import.in.model",
          label: "Converted canonical model",
        },
        {
          labelKey: "cases.quantities_from_bim.step.import.in.geometry",
          label: "Solid element geometry",
        },
      ],
      outputs: [
        {
          labelKey: "cases.quantities_from_bim.step.import.out.quantities",
          label: "Element quantities",
        },
        {
          labelKey: "cases.quantities_from_bim.step.import.out.elements",
          label: "Elements by category",
        },
      ],
      titleKey: "cases.quantities_from_bim.step.import.title",
      titleDefault: "Open the model",
      whatKey: "cases.quantities_from_bim.step.import.what",
      whatDefault:
        "Open the converted model in the viewer and browse elements by category and by level. Areas, volumes and lengths are computed from the solid geometry, not counted off a sheet by eye.",
      whyKey: "cases.quantities_from_bim.step.import.why",
      whyDefault:
        "A quantity read from the model ties back to a specific element you can select and inspect. When the design moves, you re-read the geometry instead of measuring the whole thing again.",
      moduleLabel: "BIM",
      moduleLabelKey: "nav.bim_viewer",
      to: "/projects/:projectId/bim",
    },
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.quantities_from_bim.step.boq.in.quantities",
          label: "Element quantities",
        },
        {
          labelKey: "cases.quantities_from_bim.step.boq.in.rates",
          label: "Unit rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.quantities_from_bim.step.boq.out.positions",
          label: "Priced bill positions",
        },
        {
          labelKey: "cases.quantities_from_bim.step.boq.out.links",
          label: "Live element links",
        },
      ],
      titleKey: "cases.quantities_from_bim.step.boq.title",
      titleDefault: "Carry them into a bill",
      whatKey: "cases.quantities_from_bim.step.boq.what",
      whatDefault:
        "Map the model quantities onto bill positions and apply your rates. Each position keeps a live link back to the elements it was drawn from.",
      whyKey: "cases.quantities_from_bim.step.boq.why",
      whyDefault:
        "That link from a priced line to a model element is the audit trail. Anyone reviewing the bill can trace a number back to the design and check it, rather than take it on trust.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.quantities_from_bim.step.validate.in.positions",
          label: "Mapped bill positions",
        },
        {
          labelKey: "cases.quantities_from_bim.step.validate.in.rules",
          label: "Validation rules",
        },
      ],
      outputs: [
        {
          labelKey: "cases.quantities_from_bim.step.validate.out.report",
          label: "Validation report",
        },
        {
          labelKey: "cases.quantities_from_bim.step.validate.out.gaps",
          label: "Flagged unmapped elements",
        },
      ],
      titleKey: "cases.quantities_from_bim.step.validate.title",
      titleDefault: "Validate the take-off",
      whatKey: "cases.quantities_from_bim.step.validate.what",
      whatDefault:
        "Run the validation rules to confirm the mapped quantities are complete and consistent, and that a classification is present wherever the rule set demands one.",
      whyKey: "cases.quantities_from_bim.step.validate.why",
      whyDefault:
        "A model can look complete and still miss the one property you need to price. Validation catches the unmapped element and the blank classification before the bill reaches the client.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
  ],
};

export default playbook;
