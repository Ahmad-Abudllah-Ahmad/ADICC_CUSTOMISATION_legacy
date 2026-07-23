// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Inspect work and close a non-conformance".
//
// The quality loop: inspect against criteria, raise an NCR when work fails,
// track the fix and re-inspect to close it out. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "inspect-and-close-ncr",
  order: 55,
  category: "quality",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "BadgeCheck",
  titleKey: "cases.inspect_and_close_ncr.title",
  titleDefault: "Inspect work and close a non-conformance",
  descKey: "cases.inspect_and_close_ncr.desc",
  descDefault:
    "Inspect the work against its acceptance criteria, raise a non-conformance the moment it fails, drive the correction and re-inspect so the record shows the defect proven fixed.",
  estMinutes: 10,
  steps: [
    {
      id: "inspect",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.inspect.in.checklist",
          label: "Inspection checklist",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.inspect.in.criteria",
          label: "Acceptance criteria",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.inspect.in.work",
          label: "Completed work",
        },
      ],
      outputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.inspect.out.record",
          label: "Signed inspection record",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.inspect.out.results",
          label: "Pass/fail marks",
        },
      ],
      titleKey: "cases.inspect_and_close_ncr.step.inspect.title",
      titleDefault: "Inspect the work",
      whatKey: "cases.inspect_and_close_ncr.step.inspect.what",
      whatDefault:
        "Work through the inspection checklist point by point and mark each as pass or fail, adding a photo where the state of the work needs showing. A hold point stops the next operation until it is signed, and a witness point brings the client or engineer to see it before you move on.",
      whyKey: "cases.inspect_and_close_ncr.step.inspect.why",
      whyDefault:
        "Checking against written criteria replaces opinion with a standard both sides already agreed. The signed record shows exactly what was examined, who examined it and which specification it was measured against.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "ncr",
      icon: "AlertTriangle",
      inputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.ncr.in.failure",
          label: "Failed inspection",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.ncr.in.photos",
          label: "Defect photos",
        },
      ],
      outputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.ncr.out.ncr",
          label: "Logged NCR",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.ncr.out.owner",
          label: "Named owner & due date",
        },
      ],
      titleKey: "cases.inspect_and_close_ncr.step.ncr.title",
      titleDefault: "Raise a non-conformance",
      whatKey: "cases.inspect_and_close_ncr.step.ncr.what",
      whatDefault:
        "On a failure, raise the NCR straight from the inspection. Set out the defect plainly, attach the photos and the failed checklist, and name the party who must put it right and the date it is due.",
      whyKey: "cases.inspect_and_close_ncr.step.ncr.why",
      whyDefault:
        "An NCR converts a loose complaint into a tracked action with a named owner and a due date. A defect mentioned in passing gets built over and buried, while a defect on the register gets chased until it is corrected.",
      moduleLabel: "NCR",
      moduleLabelKey: "ncr.title",
      to: "/projects/:projectId/ncr",
    },
    {
      id: "close",
      icon: "BadgeCheck",
      inputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.close.in.ncr",
          label: "Open NCR",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.close.in.fix",
          label: "Completed correction",
        },
      ],
      outputs: [
        {
          labelKey: "cases.inspect_and_close_ncr.step.close.out.closed",
          label: "Closed NCR",
        },
        {
          labelKey: "cases.inspect_and_close_ncr.step.close.out.evidence",
          label: "Closing evidence",
        },
      ],
      titleKey: "cases.inspect_and_close_ncr.step.close.title",
      titleDefault: "Re-inspect and close",
      whatKey: "cases.inspect_and_close_ncr.step.close.what",
      whatDefault:
        "When the fix is reported complete, go back and re-inspect the same points. If they now pass, close the NCR with the closing photos and sign-off attached so the trail runs from raised to resolved.",
      whyKey: "cases.inspect_and_close_ncr.step.close.why",
      whyDefault:
        "A non-conformance closes on proof, not on a promise that it was dealt with. That closing evidence is exactly what the handover pack and the client auditor will look for later.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
