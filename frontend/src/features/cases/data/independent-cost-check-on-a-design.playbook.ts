// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Provide an independent cost check on a design".
//
// A cost consultant case: take a design or an accepted tender you did not
// price yourself, benchmark it honestly against the cost base, and issue a
// second opinion the client can trust. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "independent-cost-check-on-a-design",
  order: 250,
  category: "estimating",
  companyTypes: ["cost-consultant", "developer-client", "designer"],
  icon: "Scale",
  titleKey: "cases.independent_cost_check_on_a_design.title",
  titleDefault: "Provide an independent cost check on a design",
  descKey: "cases.independent_cost_check_on_a_design.desc",
  descDefault:
    "Take a design or an accepted tender you did not price yourself, benchmark it honestly against the cost base, and issue a second opinion the client can trust.",
  estMinutes: 10,
  steps: [
    {
      id: "open",
      icon: "FileSpreadsheet",
      inputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.open.in.bill",
          label: "Design bill",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.open.in.price",
          label: "Accepted tender price",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.open.out.scope",
          label: "Understood scope",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.open.out.rates",
          label: "Quantities and rates",
        },
      ],
      titleKey: "cases.independent_cost_check_on_a_design.step.open.title",
      titleDefault: "Open the design or accepted price",
      whatKey: "cases.independent_cost_check_on_a_design.step.open.what",
      whatDefault:
        "Pull up the bill or the accepted tender figure you are being asked to check, and read its scope, quantities and the rates it was built on.",
      whyKey: "cases.independent_cost_check_on_a_design.step.open.why",
      whyDefault:
        "You cannot give an honest second opinion without first understanding exactly what the number in front of you actually covers.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
    {
      id: "benchmark",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.benchmark.in.rates",
          label: "Big-value rates",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.benchmark.in.base",
          label: "Reference cost base",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.benchmark.in.comps",
          label: "Comparable projects",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.benchmark.out.comparison",
          label: "Benchmark comparison",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.benchmark.out.variances",
          label: "Rate variances",
        },
      ],
      titleKey: "cases.independent_cost_check_on_a_design.step.benchmark.title",
      titleDefault: "Benchmark it independently",
      whatKey: "cases.independent_cost_check_on_a_design.step.benchmark.what",
      whatDefault:
        "Set the big-value rates and the overall cost per square metre against the reference cost base and comparable projects, independent of the figures already in the bill.",
      whyKey: "cases.independent_cost_check_on_a_design.step.benchmark.why",
      whyDefault:
        "An independent check that just re-reads the same source proves nothing. Comparing against a separate reference base is what gives the opinion any weight.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.report.in.comparison",
          label: "Benchmark comparison",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.report.in.variances",
          label: "Flagged rate variances",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.report.out.report",
          label: "Second opinion report",
        },
        {
          labelKey:
            "cases.independent_cost_check_on_a_design.step.report.out.recommendation",
          label: "Reliance recommendation",
        },
      ],
      titleKey: "cases.independent_cost_check_on_a_design.step.report.title",
      titleDefault: "Issue the second opinion",
      whatKey: "cases.independent_cost_check_on_a_design.step.report.what",
      whatDefault:
        "Write up where the price sits against the benchmark, name any rate that looks out of line, and give a plain recommendation on whether the figure can be relied on.",
      whyKey: "cases.independent_cost_check_on_a_design.step.report.why",
      whyDefault:
        "A client asking for an independent check wants a clear answer, not a repeat of the numbers they already have. A plain recommendation is what the report is actually for.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
