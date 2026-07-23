// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Issue a permit to work".
//
// Raise a permit to work, tie it to the safe system of work behind it, and
// close it out in the site record so the high-risk task is controlled end to end.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "issue-a-permit-to-work",
  order: 312,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "ShieldCheck",
  titleKey: "cases.issue_a_permit_to_work.title",
  titleDefault: "Issue a permit to work",
  descKey: "cases.issue_a_permit_to_work.desc",
  descDefault:
    "Raise a permit to work, tie it to its safe system of work, and close it out in the record.",
  estMinutes: 7,
  steps: [
    {
      id: "raise-permit",
      icon: "FileSignature",
      inputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.raise-permit.in.task",
          label: "High-risk task",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.raise-permit.in.hazards",
          label: "Task hazards",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.raise-permit.out.permit",
          label: "Live permit",
        },
        {
          labelKey:
            "cases.issue_a_permit_to_work.step.raise-permit.out.controls",
          label: "Controls & validity window",
        },
      ],
      titleKey: "cases.issue_a_permit_to_work.step.raise-permit.title",
      titleDefault: "Raise the permit",
      whatKey: "cases.issue_a_permit_to_work.step.raise-permit.what",
      whatDefault:
        "In HSE Advanced, raise the permit for the task, hot works, confined space or work at height, and set its controls and validity window.",
      whyKey: "cases.issue_a_permit_to_work.step.raise-permit.why",
      whyDefault:
        "High-risk work without a live permit and clear controls is how people get hurt and how the job gets shut down. The window keeps it valid only while the controls hold.",
      moduleLabel: "HSE Advanced",
      to: "/projects/:projectId/hse-advanced",
    },
    {
      id: "link-rams",
      icon: "ShieldAlert",
      inputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.link-rams.in.permit",
          label: "Live permit",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.link-rams.in.method",
          label: "Method statement",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.link-rams.in.risk",
          label: "Risk assessment",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.link-rams.out.linked",
          label: "Permit linked to RAMS",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.link-rams.out.method",
          label: "Agreed safe method",
        },
      ],
      titleKey: "cases.issue_a_permit_to_work.step.link-rams.title",
      titleDefault: "Link the RAMS",
      whatKey: "cases.issue_a_permit_to_work.step.link-rams.what",
      whatDefault:
        "Link the method statement and risk assessment that sit behind the permit so the crew works to an agreed method.",
      whyKey: "cases.issue_a_permit_to_work.step.link-rams.why",
      whyDefault:
        "A permit with no method statement or risk assessment behind it will not stand up after an incident or an audit. It proves the controls were planned, not invented on the day.",
      moduleLabel: "Safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "close-out",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.close-out.in.permit",
          label: "Active permit",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.close-out.in.workers",
          label: "Workers on task",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_a_permit_to_work.step.close-out.out.entry",
          label: "Diary entry",
        },
        {
          labelKey: "cases.issue_a_permit_to_work.step.close-out.out.closed",
          label: "Closed permit record",
        },
      ],
      titleKey: "cases.issue_a_permit_to_work.step.close-out.title",
      titleDefault: "Record and close out",
      whatKey: "cases.issue_a_permit_to_work.step.close-out.what",
      whatDefault:
        "In the Daily Diary, record who worked under the permit and the time it was closed and handed back.",
      whyKey: "cases.issue_a_permit_to_work.step.close-out.why",
      whyDefault:
        "If a fire or a near miss follows hot works, you need to show who was there and when the area was made safe. A closed permit with no diary entry leaves that gap open.",
      moduleLabel: "Daily Diary",
      to: "/projects/:projectId/daily-diary",
    },
  ],
};

export default playbook;
