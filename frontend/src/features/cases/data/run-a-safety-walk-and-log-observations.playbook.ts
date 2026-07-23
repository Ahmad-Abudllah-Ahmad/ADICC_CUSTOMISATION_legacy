// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a safety walk and log observations".
//
// Catch the hazards before they hurt someone: walk the site against a checklist,
// raise the unsafe conditions as trackable actions, and report the trend.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-safety-walk-and-log-observations",
  order: 290,
  category: "quality",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "ShieldCheck",
  titleKey: "cases.run_a_safety_walk_and_log_observations.title",
  titleDefault: "Run a safety walk and log observations",
  descKey: "cases.run_a_safety_walk_and_log_observations.desc",
  descDefault:
    "Catch the hazards before they hurt someone: walk the site against a checklist, raise the unsafe conditions as trackable actions, and report the trend to the team.",
  longDescKey: "cases.run_a_safety_walk_and_log_observations.longdesc",
  longDescDefault:
    "A safety walk that lives in a notebook fixes nothing and proves nothing when an inspector calls. This case walks the site against a checklist, turns every unsafe condition into a tracked action with an owner and a date, and reports the trend so the team sees whether the site is getting safer or the same hazards keep coming back.",
  estMinutes: 7,
  steps: [
    {
      id: "walk",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.walk.in.checklist",
          label: "Safety checklist",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.walk.in.areas",
          label: "Work areas",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.walk.out.observations",
          label: "Recorded observations",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.walk.out.findings",
          label: "Positive and negative findings",
        },
      ],
      titleKey: "cases.run_a_safety_walk_and_log_observations.step.walk.title",
      titleDefault: "Walk the site against a checklist",
      whatKey: "cases.run_a_safety_walk_and_log_observations.step.walk.what",
      whatDefault:
        "Walk the active areas against the safety checklist, record what you see with photos, and note the good practice as well as the hazards so the record is a fair picture of the site.",
      whyKey: "cases.run_a_safety_walk_and_log_observations.step.walk.why",
      whyDefault:
        "A safety walk carried in your head is one nobody can act on or learn from. Recording each observation against a checklist is what turns a stroll round site into evidence and action.",
      moduleLabel: "Inspections",
      moduleLabelKey: "nav.inspections",
      to: "/projects/:projectId/inspections",
    },
    {
      id: "raise",
      icon: "ShieldAlert",
      inputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.raise.in.findings",
          label: "Negative findings",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.raise.in.parties",
          label: "Responsible parties",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.raise.out.actions",
          label: "Logged actions",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.raise.out.owners",
          label: "Assigned owners",
        },
      ],
      titleKey: "cases.run_a_safety_walk_and_log_observations.step.raise.title",
      titleDefault: "Raise the unsafe conditions",
      whatKey: "cases.run_a_safety_walk_and_log_observations.step.raise.what",
      whatDefault:
        "Turn each unsafe condition into a tracked action against the party that owns it, with a date to close by and the risk noted, so the hazard is chased down rather than forgotten.",
      whyKey: "cases.run_a_safety_walk_and_log_observations.step.raise.why",
      whyDefault:
        "An observed hazard with no owner and no date is one that is still there next week. Raising it as a tracked action is what actually gets the guard rail fixed and gives you proof you acted.",
      moduleLabel: "Non-conformance",
      moduleLabelKey: "ncr.title",
      to: "/projects/:projectId/ncr",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.report.in.actions",
          label: "Logged actions",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.report.in.history",
          label: "Past observations",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.report.out.trend",
          label: "Safety trend report",
        },
        {
          labelKey:
            "cases.run_a_safety_walk_and_log_observations.step.report.out.open",
          label: "Open action list",
        },
      ],
      titleKey: "cases.run_a_safety_walk_and_log_observations.step.report.title",
      titleDefault: "Report the safety trend",
      whatKey: "cases.run_a_safety_walk_and_log_observations.step.report.what",
      whatDefault:
        "Report the observations and their close-out over time, showing which hazards recur and how fast actions are closed, and share it with the team at the next brief.",
      whyKey: "cases.run_a_safety_walk_and_log_observations.step.report.why",
      whyDefault:
        "One walk tells you about one day; the trend tells you whether the site is actually getting safer. Reporting it is what turns individual observations into the pressure that changes behaviour.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
