// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "As-built and O and M handover".
//
// Gather the as-built record, confirm the quality file is complete, then issue
// the operation and maintenance package the operator will actually use.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "as-built-and-om-handover",
  order: 115,
  category: "handover",
  companyTypes: [
    "general-contractor",
    "designer",
    "owner-operator",
    "bim-consultant",
  ],
  icon: "BookOpen",
  titleKey: "cases.as_built_and_om_handover.title",
  titleDefault: "As-built and O and M handover",
  descKey: "cases.as_built_and_om_handover.desc",
  descDefault:
    "Pull the as-built record together, prove the quality file has no gaps, then issue an operation and maintenance package the operator can actually run the building from.",
  estMinutes: 12,
  steps: [
    {
      id: "asbuilt",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.asbuilt.in.drawings",
          label: "As-built drawings",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.asbuilt.in.docs",
          label: "Datasheets & warranties",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.asbuilt.in.changes",
          label: "Field changes",
        },
      ],
      outputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.asbuilt.out.record",
          label: "Structured as-built record",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.asbuilt.out.library",
          label: "System-indexed files",
        },
      ],
      titleKey: "cases.as_built_and_om_handover.step.asbuilt.title",
      titleDefault: "Gather the as-built record",
      whatKey: "cases.as_built_and_om_handover.step.asbuilt.what",
      whatDefault:
        "Gather the as-built drawings, product datasheets, warranties and manuals into the project files, structured by system so a facilities engineer can find a valve or a fan five years on.",
      whyKey: "cases.as_built_and_om_handover.step.asbuilt.why",
      whyDefault:
        "The operator runs this building off your record for the next few decades. As-built has to mean what the fitters actually installed, field changes and all, not the pristine version once on the drawing.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "quality",
      icon: "FileCheck",
      inputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.quality.in.records",
          label: "Inspection & test records",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.quality.in.ncr",
          label: "NCR register",
        },
      ],
      outputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.quality.out.file",
          label: "Complete quality file",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.quality.out.clear",
          label: "No open NCRs",
        },
      ],
      titleKey: "cases.as_built_and_om_handover.step.quality.title",
      titleDefault: "Confirm the quality file",
      whatKey: "cases.as_built_and_om_handover.step.quality.what",
      whatDefault:
        "Verify the inspection records, test and commissioning certificates and material approvals are all present, and confirm not a single non-conformance is left sitting open.",
      whyKey: "cases.as_built_and_om_handover.step.quality.why",
      whyDefault:
        "The quality file is the evidence the building is safe and fit to occupy. A missing fire-damper certificate is exactly the gap an insurer or the client lawyer turns up long after the crew has gone.",
      moduleLabel: "Quality management",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "issue",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.issue.in.record",
          label: "As-built record",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.issue.in.gates",
          label: "Handover gate checklist",
        },
      ],
      outputs: [
        {
          labelKey: "cases.as_built_and_om_handover.step.issue.out.package",
          label: "Signed O&M package",
        },
        {
          labelKey: "cases.as_built_and_om_handover.step.issue.out.defects",
          label: "Defects period started",
        },
      ],
      titleKey: "cases.as_built_and_om_handover.step.issue.title",
      titleDefault: "Issue the O and M package",
      whatKey: "cases.as_built_and_om_handover.step.issue.what",
      whatDefault:
        "Assemble the close-out package, check every handover gate and outstanding-item list is cleared, and issue the signed operation and maintenance set to the operator.",
      whyKey: "cases.as_built_and_om_handover.step.issue.why",
      whyDefault:
        "A clean handover discharges the contract and starts the defects liability period on solid ground. It is also the last thing the client remembers, and it colours the next job they send your way.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
  ],
};

export default playbook;
