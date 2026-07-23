// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Mark up and compare a drawing revision".
//
// Open the live drawing revision, redline it with comments for the design
// team, then overlay the new revision on the superseded one to see exactly
// what moved. Content strings are key plus inline English default and live
// only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "mark-up-and-compare-a-drawing-revision",
  order: 330,
  category: "site",
  companyTypes: ["general-contractor", "designer", "bim-consultant"],
  icon: "Layers",
  titleKey: "cases.mark_up_and_compare_a_drawing_revision.title",
  titleDefault: "Mark up and compare a drawing revision",
  descKey: "cases.mark_up_and_compare_a_drawing_revision.desc",
  descDefault:
    "Open the current drawing revision, redline it with comments for the design team, and overlay the new revision on the superseded one to see exactly what changed and where.",
  estMinutes: 8,
  steps: [
    {
      id: "open",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.open.in.files",
          label: "Project drawing files",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.open.in.sheet",
          label: "Sheet reference",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.open.out.sheet",
          label: "Live drawing sheet",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.open.out.status",
          label: "Confirmed revision & date",
        },
      ],
      titleKey: "cases.mark_up_and_compare_a_drawing_revision.step.open.title",
      titleDefault: "Open the current drawing revision",
      whatKey: "cases.mark_up_and_compare_a_drawing_revision.step.open.what",
      whatDefault:
        "Find the sheet in the project files and open its latest revision, checking the revision letter and date so you are marking up the live drawing and not a superseded one.",
      whyKey: "cases.mark_up_and_compare_a_drawing_revision.step.open.why",
      whyDefault:
        "A markup on last month sheet is wasted the moment it lands, and worse, it can send the design team correcting a detail that has already moved on. Start from the controlled current revision every time.",
      moduleLabel: "Files",
      to: "/projects/:projectId/files",
    },
    {
      id: "redline",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.redline.in.sheet",
          label: "Live drawing sheet",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.redline.in.issues",
          label: "Site clashes & queries",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.redline.out.markup",
          label: "Redlined sheet",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.redline.out.comments",
          label: "Design queries",
        },
      ],
      titleKey:
        "cases.mark_up_and_compare_a_drawing_revision.step.redline.title",
      titleDefault: "Redline the drawing",
      whatKey: "cases.mark_up_and_compare_a_drawing_revision.step.redline.what",
      whatDefault:
        "Mark up the sheet with clouds, dimensions and comments wherever the drawing clashes with site or needs a design answer, and address each note to the design team.",
      whyKey: "cases.mark_up_and_compare_a_drawing_revision.step.redline.why",
      whyDefault:
        "A clear redline on the actual drawing tells the designer exactly where and what, so the query comes back as a proper revision instead of a vague email thread that drags on for weeks.",
      moduleLabel: "Markups",
      to: "/markups",
    },
    {
      id: "compare",
      icon: "GitCompareArrows",
      inputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.compare.in.new",
          label: "New revision",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.compare.in.old",
          label: "Superseded revision",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.compare.out.overlay",
          label: "Revision overlay",
        },
        {
          labelKey:
            "cases.mark_up_and_compare_a_drawing_revision.step.compare.out.changes",
          label: "Highlighted changes",
        },
      ],
      titleKey:
        "cases.mark_up_and_compare_a_drawing_revision.step.compare.title",
      titleDefault: "Compare against the old revision",
      whatKey: "cases.mark_up_and_compare_a_drawing_revision.step.compare.what",
      whatDefault:
        "Overlay the new revision on the superseded sheet and let the tool highlight every line that moved, so you read the real change instead of trusting the revision cloud alone.",
      whyKey: "cases.mark_up_and_compare_a_drawing_revision.step.compare.why",
      whyDefault:
        "Design teams do not always cloud everything they change. Seeing the true difference is what stops a quiet dimension change from being built wrong because nobody spotted it.",
      moduleLabel: "Compare",
      to: "/markups/compare",
    },
  ],
};

export default playbook;
