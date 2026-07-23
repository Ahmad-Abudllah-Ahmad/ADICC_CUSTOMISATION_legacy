// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Check the asset data drop before handover".
//
// Make sure the model hands over usable asset data: read what the BIM carries,
// check it against the requirements, and load only the records that pass.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "check-the-asset-data-drop-before-handover",
  order: 276,
  category: "handover",
  companyTypes: ["bim-consultant", "owner-operator"],
  icon: "FileCheck",
  titleKey: "cases.check_the_asset_data_drop_before_handover.title",
  titleDefault: "Check the asset data drop before handover",
  descKey: "cases.check_the_asset_data_drop_before_handover.desc",
  descDefault:
    "Make sure the model hands over usable asset data: read what the BIM carries, check it against the information requirements, and load only the assets that pass into the register.",
  longDescKey: "cases.check_the_asset_data_drop_before_handover.longdesc",
  longDescDefault:
    "An operator who inherits a model full of blank asset fields gets a digital twin they cannot actually run the building with. This case reads the asset data the model carries, checks each required property against what the handover asked for, and lets only the records that pass flow into the asset register so the twin starts clean instead of full of holes.",
  estMinutes: 8,
  steps: [
    {
      id: "model",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.model.in.model",
          label: "Federated model",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.model.in.requirements",
          label: "Asset information requirements",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.model.out.properties",
          label: "Asset property list",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.model.out.completeness",
          label: "Data completeness view",
        },
      ],
      titleKey:
        "cases.check_the_asset_data_drop_before_handover.step.model.title",
      titleDefault: "Read the asset data the model carries",
      whatKey:
        "cases.check_the_asset_data_drop_before_handover.step.model.what",
      whatDefault:
        "Open the model and list the assets it holds with the data attached to each, from make and model to serial, warranty and the maintainable-item flags the operator needs.",
      whyKey: "cases.check_the_asset_data_drop_before_handover.step.model.why",
      whyDefault:
        "You cannot check data you have not looked at. Reading straight from the model is what shows whether the designer's promise of a data-rich handover survived into the file you were actually given.",
      moduleLabel: "BIM",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
    {
      id: "check",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.check.in.properties",
          label: "Asset property list",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.check.in.required",
          label: "Required property set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.check.out.result",
          label: "Pass and fail list",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.check.out.defects",
          label: "Data defect log",
        },
      ],
      titleKey:
        "cases.check_the_asset_data_drop_before_handover.step.check.title",
      titleDefault: "Check it against the requirements",
      whatKey:
        "cases.check_the_asset_data_drop_before_handover.step.check.what",
      whatDefault:
        "Run each asset's properties against the required set, flag the blanks and the wrong formats, and log the failures back to whoever owns the model to fix before handover, not after.",
      whyKey: "cases.check_the_asset_data_drop_before_handover.step.check.why",
      whyDefault:
        "Handover is the last moment you have leverage to get the data fixed for free. A defect list raised now is corrected by the delivery team; the same gap found next month is your problem to chase and fund.",
      moduleLabel: "QMS",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "register",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.register.in.result",
          label: "Pass and fail list",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.register.in.approved",
          label: "Approved asset records",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.register.out.register",
          label: "Populated asset register",
        },
        {
          labelKey:
            "cases.check_the_asset_data_drop_before_handover.step.register.out.source",
          label: "Traceable data source",
        },
      ],
      titleKey:
        "cases.check_the_asset_data_drop_before_handover.step.register.title",
      titleDefault: "Load the passing assets into the register",
      whatKey:
        "cases.check_the_asset_data_drop_before_handover.step.register.what",
      whatDefault:
        "Bring the assets that passed the check into the register with their data intact, and hold back the ones that failed until they are corrected, so the register never inherits a known-bad record.",
      whyKey:
        "cases.check_the_asset_data_drop_before_handover.step.register.why",
      whyDefault:
        "The register is what the whole FM operation runs off, so a bad record there spreads into every work order and report. Loading only the passing data keeps the single source of truth actually trustworthy.",
      moduleLabel: "Assets",
      moduleLabelKey: "nav.assets",
      to: "/assets",
    },
  ],
};

export default playbook;
