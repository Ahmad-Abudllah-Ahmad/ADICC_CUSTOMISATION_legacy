// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Issue a controlled drawing revision".
//
// Register the new revision, transmit it to the trades who build from it, and
// make sure the workface is holding the current sheet and not the old one.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "issue-a-controlled-drawing-revision",
  order: 175,
  category: "site",
  companyTypes: ["designer", "general-contractor", "bim-consultant"],
  icon: "FolderOpen",
  titleKey: "cases.issue_a_controlled_drawing_revision.title",
  titleDefault: "Issue a controlled drawing revision",
  descKey: "cases.issue_a_controlled_drawing_revision.desc",
  descDefault:
    "Register a new drawing revision, mark the old one superseded, transmit it to every trade that builds from it, and confirm the current sheet is the one on the wall at the workface.",
  estMinutes: 8,
  steps: [
    {
      id: "register",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.register.in.drawing",
          label: "New drawing revision",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.register.in.register",
          label: "Document register",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.register.out.registered",
          label: "Registered revision",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.register.out.superseded",
          label: "Old sheet superseded",
        },
      ],
      titleKey: "cases.issue_a_controlled_drawing_revision.step.register.title",
      titleDefault: "Register the new revision",
      whatKey: "cases.issue_a_controlled_drawing_revision.step.register.what",
      whatDefault:
        "Load the new revision into the document register with its number, date and revision letter, mark the previous version superseded, and note what changed so a reader knows why it moved.",
      whyKey: "cases.issue_a_controlled_drawing_revision.step.register.why",
      whyDefault:
        "Two live copies of the same drawing is how a wall gets built to last month geometry. One controlled register, with the old revision plainly retired, is what leaves no doubt which sheet is the truth.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "transmit",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.transmit.in.revision",
          label: "Registered revision",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.transmit.in.recipients",
          label: "Trade distribution list",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.transmit.out.transmittal",
          label: "Issued transmittal",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.transmit.out.record",
          label: "Delivery record",
        },
      ],
      titleKey: "cases.issue_a_controlled_drawing_revision.step.transmit.title",
      titleDefault: "Transmit it to the trades",
      whatKey: "cases.issue_a_controlled_drawing_revision.step.transmit.what",
      whatDefault:
        "Send a transmittal to every trade and subcontractor working off that drawing, listing the revision issued and the date, and keep the record of who it went to and when.",
      whyKey: "cases.issue_a_controlled_drawing_revision.step.transmit.why",
      whyDefault:
        "A revision that sits in the register but never reaches the gang who pours the slab has changed nothing. The transmittal record is also your proof that the trade had the current information when they built it.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "verify",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.verify.in.current",
          label: "Latest revision",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.verify.in.posted",
          label: "Sheets at workface",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.verify.out.confirmed",
          label: "Current sheet confirmed",
        },
        {
          labelKey:
            "cases.issue_a_controlled_drawing_revision.step.verify.out.removed",
          label: "Superseded sheets pulled",
        },
      ],
      titleKey: "cases.issue_a_controlled_drawing_revision.step.verify.title",
      titleDefault: "Verify the current sheet on site",
      whatKey: "cases.issue_a_controlled_drawing_revision.step.verify.what",
      whatDefault:
        "On the walk, check the drawings pinned up at the work area and in the trade cabins carry the latest revision, and pull down every superseded sheet you find still in use.",
      whyKey: "cases.issue_a_controlled_drawing_revision.step.verify.why",
      whyDefault:
        "A superseded drawing left on the wall keeps building the old detail no matter how clean your register is. Clearing it at the source is the cheapest defect you will ever prevent.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
