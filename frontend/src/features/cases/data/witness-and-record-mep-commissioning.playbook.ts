// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Witness and record MEP commissioning".
//
// Prove the services actually work before handover: set the commissioning
// checks, witness each system live, and file the certificates the operator needs.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "witness-and-record-mep-commissioning",
  order: 280,
  category: "quality",
  companyTypes: ["general-contractor", "owner-operator"],
  stage: "handover",
  icon: "ClipboardCheck",
  titleKey: "cases.witness_and_record_mep_commissioning.title",
  titleDefault: "Witness and record MEP commissioning",
  descKey: "cases.witness_and_record_mep_commissioning.desc",
  descDefault:
    "Prove the services actually work before handover: set the commissioning checks, witness each system live, and file the certificates the operator will need.",
  longDescKey: "cases.witness_and_record_mep_commissioning.longdesc",
  longDescDefault:
    "Services that were never witnessed running are services the operator discovers are broken on the first cold morning. This case sets the commissioning checks against each MEP system, has them witnessed live so the result is seen and not just claimed, and files the signed certificates so the building hands over with proof its plant performs to spec.",
  estMinutes: 9,
  steps: [
    {
      id: "plan",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.plan.in.systems",
          label: "MEP systems list",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.plan.in.design",
          label: "Design performance data",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.plan.out.checklist",
          label: "Commissioning checklist",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.plan.out.criteria",
          label: "Acceptance criteria",
        },
      ],
      titleKey: "cases.witness_and_record_mep_commissioning.step.plan.title",
      titleDefault: "Set the commissioning checks",
      whatKey: "cases.witness_and_record_mep_commissioning.step.plan.what",
      whatDefault:
        "For each MEP system, set the checks that prove it meets the design, from flow rates to alarm responses, with the pass criteria written down before anyone switches it on.",
      whyKey: "cases.witness_and_record_mep_commissioning.step.plan.why",
      whyDefault:
        "A commissioning check with no agreed pass mark is an argument waiting to happen. Setting the criteria up front is what lets the witness say pass or fail on the day instead of debating it.",
      moduleLabel: "QMS",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "witness",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.witness.in.checklist",
          label: "Commissioning checklist",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.witness.in.system",
          label: "Live system",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.witness.out.results",
          label: "Witnessed results",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.witness.out.snags",
          label: "Snags raised",
        },
      ],
      titleKey: "cases.witness_and_record_mep_commissioning.step.witness.title",
      titleDefault: "Witness each system live",
      whatKey: "cases.witness_and_record_mep_commissioning.step.witness.what",
      whatDefault:
        "Stand at each system while it runs the checks, record the readings against the criteria, pass what meets spec and raise a snag on what does not, with evidence captured on the spot.",
      whyKey: "cases.witness_and_record_mep_commissioning.step.witness.why",
      whyDefault:
        "A certificate signed off a desk proves nothing. Witnessing the system live is the only way to know the pump actually delivers and the alarm actually sounds before the operator is relying on it.",
      moduleLabel: "Inspections",
      moduleLabelKey: "nav.inspections",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "record",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.record.in.results",
          label: "Witnessed results",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.record.in.certificates",
          label: "System certificates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.record.out.file",
          label: "Commissioning file",
        },
        {
          labelKey:
            "cases.witness_and_record_mep_commissioning.step.record.out.pack",
          label: "Operator evidence pack",
        },
      ],
      titleKey: "cases.witness_and_record_mep_commissioning.step.record.title",
      titleDefault: "File the commissioning records",
      whatKey: "cases.witness_and_record_mep_commissioning.step.record.what",
      whatDefault:
        "Gather the signed certificates, the witnessed results and the equipment data into the commissioning file, filed where the operator and the O&M manual can point straight to it.",
      whyKey: "cases.witness_and_record_mep_commissioning.step.record.why",
      whyDefault:
        "Commissioning proof scattered across inboxes is proof the operator cannot find when a system fails under warranty. A single filed pack is what backs a warranty claim and shows the building was handed over working.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
