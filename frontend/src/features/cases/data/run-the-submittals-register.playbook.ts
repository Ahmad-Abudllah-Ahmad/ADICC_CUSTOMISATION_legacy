// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run the submittals register".
//
// Log shop drawings and technical submittals, check each one against spec,
// issue it for review, and surface anything overdue before it stalls procurement.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-the-submittals-register",
  order: 314,
  category: "quality",
  companyTypes: ["general-contractor", "subcontractor", "designer"],
  icon: "ClipboardList",
  titleKey: "cases.run_the_submittals_register.title",
  titleDefault: "Run the submittals register",
  descKey: "cases.run_the_submittals_register.desc",
  descDefault:
    "Log shop drawings and submittals, check them against spec, issue for review, and flag anything overdue before it stops procurement.",
  estMinutes: 10,
  steps: [
    {
      id: "log",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.run_the_submittals_register.step.log.in.drawings",
          label: "Shop drawings",
        },
        {
          labelKey: "cases.run_the_submittals_register.step.log.in.submittals",
          label: "Technical submittals",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_submittals_register.step.log.out.register",
          label: "Submittals register",
        },
        {
          labelKey: "cases.run_the_submittals_register.step.log.out.dates",
          label: "Required-by dates",
        },
      ],
      titleKey: "cases.run_the_submittals_register.step.log.title",
      titleDefault: "Log the submittals",
      whatKey: "cases.run_the_submittals_register.step.log.what",
      whatDefault:
        "In Submittals, log each shop drawing and technical submittal and set the date approval is needed by.",
      whyKey: "cases.run_the_submittals_register.step.log.why",
      whyDefault:
        "A submittal approved late holds up the order, and a late order holds up the trade on site. The register is where you see that coming.",
      moduleLabel: "Submittals",
      to: "/projects/:projectId/submittals",
    },
    {
      id: "attach-spec",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.run_the_submittals_register.step.attach-spec.in.item",
          label: "Logged submittal",
        },
        {
          labelKey:
            "cases.run_the_submittals_register.step.attach-spec.in.spec",
          label: "Specification document",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_the_submittals_register.step.attach-spec.out.clause",
          label: "Attached spec clause",
        },
        {
          labelKey:
            "cases.run_the_submittals_register.step.attach-spec.out.baseline",
          label: "Review baseline",
        },
      ],
      titleKey: "cases.run_the_submittals_register.step.attach-spec.title",
      titleDefault: "Attach the spec",
      whatKey: "cases.run_the_submittals_register.step.attach-spec.what",
      whatDefault:
        "From QMS, attach the specification clause the submittal is checked against.",
      whyKey: "cases.run_the_submittals_register.step.attach-spec.why",
      whyDefault:
        "A reviewer needs the spec next to the submittal, or the approval is just an opinion. It also settles later arguments about what was actually specified.",
      moduleLabel: "QMS",
      to: "/projects/:projectId/qms",
    },
    {
      id: "issue-review",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.run_the_submittals_register.step.issue-review.in.package",
          label: "Submittal package",
        },
        {
          labelKey:
            "cases.run_the_submittals_register.step.issue-review.in.reviewer",
          label: "Design reviewer",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_the_submittals_register.step.issue-review.out.status",
          label: "Review status",
        },
        {
          labelKey:
            "cases.run_the_submittals_register.step.issue-review.out.comments",
          label: "Review comments",
        },
      ],
      titleKey: "cases.run_the_submittals_register.step.issue-review.title",
      titleDefault: "Issue for review",
      whatKey: "cases.run_the_submittals_register.step.issue-review.what",
      whatDefault:
        "In Correspondence, issue the submittal for review and record the status that comes back, approved, approved with comments or rejected.",
      whyKey: "cases.run_the_submittals_register.step.issue-review.why",
      whyDefault:
        "The returned status is the trigger to order or to resubmit, so it has to be recorded against the item. A spoken yes does not release the procurement.",
      moduleLabel: "Correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.run_the_submittals_register.step.report.in.log",
          label: "Submittals log",
        },
        {
          labelKey: "cases.run_the_submittals_register.step.report.in.statuses",
          label: "Review statuses",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_submittals_register.step.report.out.report",
          label: "Published log",
        },
        {
          labelKey: "cases.run_the_submittals_register.step.report.out.overdue",
          label: "Overdue blockers list",
        },
      ],
      titleKey: "cases.run_the_submittals_register.step.report.title",
      titleDefault: "Report what is overdue",
      whatKey: "cases.run_the_submittals_register.step.report.what",
      whatDefault:
        "In Reports, publish the submittals log and pull out anything overdue that is blocking procurement.",
      whyKey: "cases.run_the_submittals_register.step.report.why",
      whyDefault:
        "The people ordering materials need one clear list of what is stuck and why. Overdue submittals are the quiet reason a programme slips.",
      moduleLabel: "Reports",
      to: "/reports",
    },
  ],
};

export default playbook;
