// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Report and action a near-miss".
//
// Capture the near-miss while it is fresh, work out what nearly went wrong and
// fix the cause, then prove the control is really in place. Content strings
// are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "report-and-action-a-near-miss",
  order: 190,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "ShieldAlert",
  titleKey: "cases.report_and_action_a_near_miss.title",
  titleDefault: "Report and action a near-miss",
  descKey: "cases.report_and_action_a_near_miss.desc",
  descDefault:
    "Log the near-miss while the detail is fresh, work out the cause and set the corrective action, then check on the walk that the control is actually in place.",
  estMinutes: 8,
  steps: [
    {
      id: "report",
      icon: "ShieldAlert",
      inputs: [
        {
          labelKey: "cases.report_and_action_a_near_miss.step.report.in.event",
          label: "Near-miss observation",
        },
        {
          labelKey: "cases.report_and_action_a_near_miss.step.report.in.scene",
          label: "Scene photo",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.report.out.report",
          label: "Logged near-miss",
        },
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.report.out.severity",
          label: "Potential-harm rating",
        },
      ],
      titleKey: "cases.report_and_action_a_near_miss.step.report.title",
      titleDefault: "Log the near-miss",
      whatKey: "cases.report_and_action_a_near_miss.step.report.what",
      whatDefault:
        "Record what happened, where and when, who was involved and what harm it could have caused, with a photo of the scene. Capture it the same shift, before memories fade and the scene is cleared.",
      whyKey: "cases.report_and_action_a_near_miss.step.report.why",
      whyDefault:
        "A near-miss is a free warning: the injury it points to has not happened yet. Logging it while it is fresh is what lets you fix the cause before the next time turns it into a real accident.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "action",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey: "cases.report_and_action_a_near_miss.step.action.in.report",
          label: "Logged near-miss",
        },
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.action.in.controls",
          label: "Failed control",
        },
      ],
      outputs: [
        {
          labelKey: "cases.report_and_action_a_near_miss.step.action.out.cause",
          label: "Root cause",
        },
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.action.out.action",
          label: "Corrective action",
        },
      ],
      titleKey: "cases.report_and_action_a_near_miss.step.action.title",
      titleDefault: "Find the cause and act",
      whatKey: "cases.report_and_action_a_near_miss.step.action.what",
      whatDefault:
        "Look past the immediate trigger to why the control failed, then set the corrective action with a named owner and a due date, and brief the wider crew if the same risk exists elsewhere on site.",
      whyKey: "cases.report_and_action_a_near_miss.step.action.why",
      whyDefault:
        "Blaming the person who slipped fixes nothing; the missing barrier or the bad access will catch the next worker too. Fixing the cause is what actually removes the hazard rather than moving it along.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "verify",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.report_and_action_a_near_miss.step.verify.in.action",
          label: "Corrective action",
        },
        {
          labelKey: "cases.report_and_action_a_near_miss.step.verify.in.walk",
          label: "Inspection walk",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.verify.out.verified",
          label: "Control verified",
        },
        {
          labelKey:
            "cases.report_and_action_a_near_miss.step.verify.out.closed",
          label: "Near-miss closed",
        },
      ],
      titleKey: "cases.report_and_action_a_near_miss.step.verify.title",
      titleDefault: "Verify the fix on the walk",
      whatKey: "cases.report_and_action_a_near_miss.step.verify.what",
      whatDefault:
        "Go back to the spot on the next inspection walk, confirm the corrective action is really done and holding, and close the near-miss with the evidence attached.",
      whyKey: "cases.report_and_action_a_near_miss.step.verify.why",
      whyDefault:
        "An action marked done in the office is not the same as a barrier standing on the ground. Checking it on the walk is what turns a good intention into protection a worker can lean on.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
