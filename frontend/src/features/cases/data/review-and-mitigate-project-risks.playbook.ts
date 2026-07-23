// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Review and mitigate the risk register".
//
// A project manager case: walk the risk register on a regular cadence, score
// likelihood and impact honestly, and assign a mitigation owner before a risk
// turns into a real problem. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "review-and-mitigate-project-risks",
  order: 260,
  category: "planning",
  companyTypes: ["project-manager", "general-contractor", "owner-operator"],
  icon: "ShieldAlert",
  titleKey: "cases.review_and_mitigate_project_risks.title",
  titleDefault: "Review and mitigate the risk register",
  descKey: "cases.review_and_mitigate_project_risks.desc",
  descDefault:
    "Walk the risk register on a regular cadence, score likelihood and impact honestly, and assign a mitigation owner before a risk turns into a real problem.",
  estMinutes: 9,
  steps: [
    {
      id: "review",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.review.in.register",
          label: "Open risk register",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.review.in.status",
          label: "Current project status",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.review.out.rescored",
          label: "Re-scored risks",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.review.out.retired",
          label: "Retired risks",
        },
      ],
      titleKey: "cases.review_and_mitigate_project_risks.step.review.title",
      titleDefault: "Walk the risk register",
      whatKey: "cases.review_and_mitigate_project_risks.step.review.what",
      whatDefault:
        "Go through every open risk on the register, re-score its likelihood and impact against what you now know, and retire anything that has genuinely passed.",
      whyKey: "cases.review_and_mitigate_project_risks.step.review.why",
      whyDefault:
        "A risk register nobody revisits just accumulates stale entries and hides the two or three that actually matter this month.",
      moduleLabel: "Risk register",
      moduleLabelKey: "nav.risks",
      to: "/risks",
    },
    {
      id: "mitigate",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.mitigate.in.risks",
          label: "Live risks",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.mitigate.in.team",
          label: "Available owners",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.mitigate.out.actions",
          label: "Mitigation actions",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.mitigate.out.owners",
          label: "Owner & date",
        },
      ],
      titleKey: "cases.review_and_mitigate_project_risks.step.mitigate.title",
      titleDefault: "Assign the mitigation",
      whatKey: "cases.review_and_mitigate_project_risks.step.mitigate.what",
      whatDefault:
        "For every risk still live, name the mitigation action, its owner and a date, rather than leaving it as a description with nobody accountable for it.",
      whyKey: "cases.review_and_mitigate_project_risks.step.mitigate.why",
      whyDefault:
        "A risk with no owner and no date is a risk that sits there until it happens. Assigning both is what actually reduces the chance it does.",
      moduleLabel: "Risk register",
      moduleLabelKey: "nav.risks",
      to: "/risks",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.report.in.current",
          label: "Updated register",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.report.in.previous",
          label: "Previous review",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.report.out.trend",
          label: "Risk trend report",
        },
        {
          labelKey:
            "cases.review_and_mitigate_project_risks.step.report.out.exposure",
          label: "Exposure summary",
        },
      ],
      titleKey: "cases.review_and_mitigate_project_risks.step.report.title",
      titleDefault: "Report the trend",
      whatKey: "cases.review_and_mitigate_project_risks.step.report.what",
      whatDefault:
        "Report how the register has moved since the last review, new risks in, old ones retired or realised, so the wider team sees the trend, not just a snapshot.",
      whyKey: "cases.review_and_mitigate_project_risks.step.report.why",
      whyDefault:
        "A single risk review tells you where you stand today. The trend across several is what tells you whether the project is getting safer or more exposed.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
