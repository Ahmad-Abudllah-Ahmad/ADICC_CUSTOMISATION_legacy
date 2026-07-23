// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get 6D carbon from a BIM model".
//
// Walks a user through the 6D flow: import a converted BIM model, open Carbon,
// run Auto-enrich from BIM (it matches element materials to carbon factors and
// pulls quantities straight from the geometry, preview first then confirm),
// review the linked entries and their match confidence, and finish by setting a
// reduction target and generating a report. It makes the brand-new 6D
// auto-enrich feature learnable end to end.
//
// Every content string is a key plus an inline English default. These stay HERE
// and are never added to en.ts (only the framework chrome lives there). Module
// chips reuse existing translated nav keys so they localize for free.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "carbon-from-bim-6d",
  order: 30,
  category: "bim",
  companyTypes: ["designer", "bim-consultant", "owner-operator"],
  icon: "Layers",
  titleKey: "cases.carbon_from_bim_6d.title",
  titleDefault: "Get 6D carbon from a BIM model",
  descKey: "cases.carbon_from_bim_6d.desc",
  descDefault:
    "Turn a converted BIM model into an embodied carbon footprint. Auto-enrich reads quantities off the geometry and pairs each material with an emission factor, then you set a reduction target and issue the report. Five steps.",
  estMinutes: 12,
  steps: [
    {
      id: "import-model",
      icon: "Building2",
      inputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.import-model.in.file",
          label: "Converted model file",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.import-model.in.project",
          label: "Project record",
        },
      ],
      outputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.import-model.out.elements",
          label: "Elements with materials",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.import-model.out.quantities",
          label: "Quantities from geometry",
        },
      ],
      titleKey: "cases.carbon_from_bim_6d.step.import-model.title",
      titleDefault: "Import a BIM model",
      whatKey: "cases.carbon_from_bim_6d.step.import-model.what",
      whatDefault:
        "Open BIM and import the converted model for this job. Once conversion finishes, every wall, slab and column carries both its material tag and the quantity measured from the solid geometry.",
      whyKey: "cases.carbon_from_bim_6d.step.import-model.why",
      whyDefault:
        "The whole footprint is read from the model, so garbage in means garbage out. A converted model hands the carbon match a clean material and a real quantity instead of a figure somebody typed by hand.",
      moduleLabel: "BIM",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
    {
      id: "inventory",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.inventory.in.model",
          label: "Imported BIM model",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.inventory.in.project",
          label: "Project record",
        },
      ],
      outputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.inventory.out.inventory",
          label: "Empty carbon inventory",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.inventory.out.boundary",
          label: "System boundary set",
        },
      ],
      titleKey: "cases.carbon_from_bim_6d.step.inventory.title",
      titleDefault: "Open Carbon and start an inventory",
      whatKey: "cases.carbon_from_bim_6d.step.inventory.what",
      whatDefault:
        "Move to Carbon and open a fresh inventory for the project. Fix the system boundary up front, cradle to gate for the shell or cradle to grave when you also need the in-use and end of life stages.",
      whyKey: "cases.carbon_from_bim_6d.step.inventory.why",
      whyDefault:
        "Boundary choice drives the whole result, so pin it down before any entry lands. Two footprints only compare when they cover the same stages, and the inventory is the one place every material line adds up.",
      moduleLabel: "Carbon",
      moduleLabelKey: "nav.carbon",
      to: "/projects/:projectId/carbon",
    },
    {
      id: "enrich",
      icon: "Sparkles",
      inputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.enrich.in.inventory",
          label: "Open inventory",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.enrich.in.materials",
          label: "Element materials",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.enrich.in.factors",
          label: "Emission factor library",
        },
      ],
      outputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.enrich.out.preview",
          label: "Preview of matched lines",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.enrich.out.entries",
          label: "Confirmed carbon entries",
        },
      ],
      titleKey: "cases.carbon_from_bim_6d.step.enrich.title",
      titleDefault: "Auto-enrich embodied carbon from BIM",
      whatKey: "cases.carbon_from_bim_6d.step.enrich.what",
      whatDefault:
        "Run Auto-enrich from BIM inside the inventory. Choose the model, look over the proposed lines in the preview, then confirm. Each element material is matched to an emission factor and the quantity is pulled straight off the geometry. Nothing is saved until you accept it.",
      whyKey: "cases.carbon_from_bim_6d.step.enrich.why",
      whyDefault:
        "This is where 6D earns its keep. Rather than keying concrete, steel and insulation one line at a time, you get a full embodied list from the model in seconds, and every row shows how sure the match is.",
      moduleLabel: "Carbon",
      moduleLabelKey: "nav.carbon",
      to: "/projects/:projectId/carbon",
    },
    {
      id: "review",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.review.in.entries",
          label: "Enriched carbon entries",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.review.in.confidence",
          label: "Match confidence flags",
        },
      ],
      outputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.review.out.verified",
          label: "Verified carbon lines",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.review.out.footprint",
          label: "Signed-off footprint",
        },
      ],
      titleKey: "cases.carbon_from_bim_6d.step.review.title",
      titleDefault: "Review the linked entries and confidence",
      whatKey: "cases.carbon_from_bim_6d.step.review.what",
      whatDefault:
        "Work down the added lines. Every entry points back to the BIM element that produced it and shows a match confidence, so open the amber and red rows first and correct the factor or the quantity where the pairing looks wrong.",
      whyKey: "cases.carbon_from_bim_6d.step.review.why",
      whyDefault:
        "The tool suggests, the estimator signs off. A generic factor on a specialist product can swing the total by tonnes, so the confidence flag tells you exactly which rows deserve a second look.",
      moduleLabel: "Carbon",
      moduleLabelKey: "nav.carbon",
      to: "/projects/:projectId/carbon",
    },
    {
      id: "target",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.target.in.footprint",
          label: "Verified footprint",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.target.in.area",
          label: "Floor area",
        },
      ],
      outputs: [
        {
          labelKey: "cases.carbon_from_bim_6d.step.target.out.target",
          label: "Reduction target",
        },
        {
          labelKey: "cases.carbon_from_bim_6d.step.target.out.report",
          label: "Carbon report",
        },
      ],
      titleKey: "cases.carbon_from_bim_6d.step.target.title",
      titleDefault: "Set a target and report",
      whatKey: "cases.carbon_from_bim_6d.step.target.what",
      whatDefault:
        "Set a reduction target, either as an absolute total or per square metre of floor area, then generate the report for the period in the framework your client asks for. The target tracks live as the inventory changes.",
      whyKey: "cases.carbon_from_bim_6d.step.target.why",
      whyDefault:
        "A raw carbon figure convinces no one on its own. A target draws the line you are trying to beat, and the exported report turns the footprint into a dated record you can put in front of an assessor or a planning officer.",
      moduleLabel: "Carbon",
      moduleLabelKey: "nav.carbon",
      to: "/projects/:projectId/carbon",
    },
  ],
};

export default playbook;
