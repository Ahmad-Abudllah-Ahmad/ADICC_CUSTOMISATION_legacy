// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Manage the defects liability period after occupation".
//
// An owner/operator case: once the building is occupied, keep every reported
// defect tracked against the contractor obliged to fix it, until the
// liability period runs out clean. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "defects-liability-period-tracking",
  order: 210,
  category: "handover",
  companyTypes: ["owner-operator", "general-contractor", "project-manager"],
  icon: "ShieldCheck",
  titleKey: "cases.defects_liability_period_tracking.title",
  titleDefault: "Manage the defects liability period after occupation",
  descKey: "cases.defects_liability_period_tracking.desc",
  descDefault:
    "Once the building is occupied, log every reported defect against the contractor and a due date, and drive the list to zero before the liability period closes.",
  estMinutes: 9,
  steps: [
    {
      id: "log",
      icon: "AlertTriangle",
      inputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.log.in.report",
          label: "Occupier defect report",
        },
        {
          labelKey: "cases.defects_liability_period_tracking.step.log.in.photo",
          label: "Location and photo",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.log.out.entry",
          label: "Logged defect entry",
        },
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.log.out.contractor",
          label: "Responsible contractor",
        },
      ],
      titleKey: "cases.defects_liability_period_tracking.step.log.title",
      titleDefault: "Log the reported defect",
      whatKey: "cases.defects_liability_period_tracking.step.log.what",
      whatDefault:
        "Add the defect reported by the occupier to the punch list with its location, a photo and the contractor or subcontractor responsible for the fix.",
      whyKey: "cases.defects_liability_period_tracking.step.log.why",
      whyDefault:
        "A defect reported to a caretaker by phone and never written down is a defect that never gets fixed. One list keeps every claim against the liability period visible.",
      moduleLabel: "Punch list",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
    {
      id: "assign",
      icon: "Users",
      inputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.assign.in.defect",
          label: "Logged defect",
        },
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.assign.in.clause",
          label: "Defects clause",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.assign.out.owner",
          label: "Assigned contractor",
        },
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.assign.out.due",
          label: "Due date set",
        },
      ],
      titleKey: "cases.defects_liability_period_tracking.step.assign.title",
      titleDefault: "Assign it and set a due date",
      whatKey: "cases.defects_liability_period_tracking.step.assign.what",
      whatDefault:
        "Assign the item to the contractor obliged to fix it under the defects clause, set a due date inside the liability period, and track it until it is marked done.",
      whyKey: "cases.defects_liability_period_tracking.step.assign.why",
      whyDefault:
        "The liability period has a hard end date, and a defect still open when it closes becomes a cost the owner absorbs. Assigning and dating each one is what keeps the obligation enforceable.",
      moduleLabel: "Punch list",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
    {
      id: "close",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.close.in.list",
          label: "Closed defect list",
        },
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.close.in.retention",
          label: "Held retention",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.close.out.certificate",
          label: "Final certificate",
        },
        {
          labelKey:
            "cases.defects_liability_period_tracking.step.close.out.retention",
          label: "Released retention",
        },
      ],
      titleKey: "cases.defects_liability_period_tracking.step.close.title",
      titleDefault: "Close the period clean",
      whatKey: "cases.defects_liability_period_tracking.step.close.what",
      whatDefault:
        "At the end of the defects liability period, confirm every item on the list is closed and issue the final certificate releasing the last retention.",
      whyKey: "cases.defects_liability_period_tracking.step.close.why",
      whyDefault:
        "A clean close at the end of the liability period is what finally discharges the contractor obligation and releases the retention held against it.",
      moduleLabel: "Close-out",
      moduleLabelKey: "nav.closeout",
      to: "/closeout",
    },
  ],
};

export default playbook;
