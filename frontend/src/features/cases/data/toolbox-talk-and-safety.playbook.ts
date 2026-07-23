// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Toolbox talk and safety check".
//
// Brief the crew on today's hazards, record who attended, then verify on the
// walk that the controls are actually in place. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "toolbox-talk-and-safety",
  order: 105,
  category: "quality",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "HardHat",
  titleKey: "cases.toolbox_talk_and_safety.title",
  titleDefault: "Toolbox talk and safety check",
  descKey: "cases.toolbox_talk_and_safety.desc",
  descDefault:
    "Brief the crew on the hazards this shift actually carries, capture who was there, then prove on the walk that the controls you agreed are really up.",
  estMinutes: 8,
  steps: [
    {
      id: "brief",
      icon: "ShieldAlert",
      inputs: [
        {
          labelKey: "cases.toolbox_talk_and_safety.step.brief.in.plan",
          label: "Shift work plan",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.brief.in.rams",
          label: "Risk assessment & method",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.brief.in.crew",
          label: "Crew on shift",
        },
      ],
      outputs: [
        {
          labelKey: "cases.toolbox_talk_and_safety.step.brief.out.briefed",
          label: "Briefed crew",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.brief.out.attendance",
          label: "Signed attendance record",
        },
      ],
      titleKey: "cases.toolbox_talk_and_safety.step.brief.title",
      titleDefault: "Run the toolbox talk",
      whatKey: "cases.toolbox_talk_and_safety.step.brief.what",
      whatDefault:
        "Talk through the specific hazards for the shift ahead, the safe method and the controls in place, then capture the attendance so every worker on the face is signed onto the brief.",
      whyKey: "cases.toolbox_talk_and_safety.step.brief.why",
      whyDefault:
        "A crew that heard the risks makes better calls the moment a scaffold looks wrong. The signed attendance is also the record that shows the talk happened if an incident is ever investigated.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "verify",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.toolbox_talk_and_safety.step.verify.in.checklist",
          label: "Safety checklist",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.verify.in.controls",
          label: "Briefed controls",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.verify.in.permits",
          label: "Live permits",
        },
      ],
      outputs: [
        {
          labelKey: "cases.toolbox_talk_and_safety.step.verify.out.verified",
          label: "Verified controls",
        },
        {
          labelKey: "cases.toolbox_talk_and_safety.step.verify.out.defects",
          label: "Logged safety shortfalls",
        },
      ],
      titleKey: "cases.toolbox_talk_and_safety.step.verify.title",
      titleDefault: "Verify the controls on the walk",
      whatKey: "cases.toolbox_talk_and_safety.step.verify.what",
      whatDefault:
        "Walk the work area against the checklist, confirm edge protection, access, exclusion zones and permits match what was briefed, and log every item that falls short with a photo.",
      whyKey: "cases.toolbox_talk_and_safety.step.verify.why",
      whyDefault:
        "A toolbox talk is only intention until the walk proves the guardrail is bolted and the permit is live. Checking the controls on the ground is what turns words into protection that actually holds.",
      moduleLabel: "Inspections",
      moduleLabelKey: "inspections.title",
      to: "/projects/:projectId/inspections",
    },
  ],
};

export default playbook;
