// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Estimate a feasibility budget before design".
//
// A developer or client case: put an order-of-magnitude number in front of a
// board before a single drawing exists, using a cost-per-square-metre
// benchmark and a shell of lump-sum allowances rather than a detailed
// take-off. Content strings are key plus inline English default and live only
// here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "feasibility-budget-before-design",
  order: 205,
  category: "estimating",
  companyTypes: ["developer-client", "cost-consultant", "general-contractor"],
  icon: "Calculator",
  titleKey: "cases.feasibility_budget_before_design.title",
  titleDefault: "Estimate a feasibility budget before design",
  descKey: "cases.feasibility_budget_before_design.desc",
  descDefault:
    "Put an order-of-magnitude number in front of the board before a single drawing exists: pull a cost-per-square-metre benchmark, shape it into a shell of allowances and report the range.",
  estMinutes: 9,
  steps: [
    {
      id: "benchmark",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.benchmark.in.brief",
          label: "Building type and region",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.benchmark.in.database",
          label: "Cost database",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.benchmark.out.rate",
          label: "Cost per square metre",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.benchmark.out.comps",
          label: "Comparable projects",
        },
      ],
      titleKey: "cases.feasibility_budget_before_design.step.benchmark.title",
      titleDefault: "Pull a cost-per-square-metre benchmark",
      whatKey: "cases.feasibility_budget_before_design.step.benchmark.what",
      whatDefault:
        "Search the cost database for comparable projects of the same building type and region, and read off the typical cost per square metre of floor area.",
      whyKey: "cases.feasibility_budget_before_design.step.benchmark.why",
      whyDefault:
        "Before a design exists, a benchmark rate is the only honest way to put a number on the job, and it tells you fast whether the brief fits the budget at all.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "allowances",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.allowances.in.rate",
          label: "Benchmark rate",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.allowances.in.area",
          label: "Gross floor area",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.allowances.out.allowances",
          label: "Element allowances",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.allowances.out.targets",
          label: "Element budget targets",
        },
      ],
      titleKey: "cases.feasibility_budget_before_design.step.allowances.title",
      titleDefault: "Shape it into a bill of allowances",
      whatKey: "cases.feasibility_budget_before_design.step.allowances.what",
      whatDefault:
        "Open the bill and lay in a handful of lump-sum allowances by element, substructure, superstructure, envelope, fit-out, services, scaled off the floor area rather than a detailed take-off.",
      whyKey: "cases.feasibility_budget_before_design.step.allowances.why",
      whyDefault:
        "A feasibility budget only needs to be right at the element level. Locking allowances now gives the design team a target to design to instead of a blank cheque.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.report.in.allowances",
          label: "Element allowances",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.report.in.assumptions",
          label: "Source and assumptions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.report.out.range",
          label: "Budget range",
        },
        {
          labelKey:
            "cases.feasibility_budget_before_design.step.report.out.report",
          label: "Feasibility report",
        },
      ],
      titleKey: "cases.feasibility_budget_before_design.step.report.title",
      titleDefault: "Report the range",
      whatKey: "cases.feasibility_budget_before_design.step.report.what",
      whatDefault:
        "Issue the budget as a range, low to high, with the benchmark source and the assumptions stated plainly, so the board can decide whether to proceed to design.",
      whyKey: "cases.feasibility_budget_before_design.step.report.why",
      whyDefault:
        "A single number invites false confidence and gets quoted back at you as a promise. A stated range with its assumptions is what a feasibility decision should actually be made on.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
