// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build an elemental cost plan".
//
// A cost consultant case: structure a cost plan by classified element rather
// than by trade, check it against the classification rules, and issue a plan
// a designer can actually work to. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "elemental-cost-plan-and-classification",
  order: 220,
  category: "estimating",
  companyTypes: ["cost-consultant", "designer", "developer-client"],
  icon: "Table2",
  titleKey: "cases.elemental_cost_plan_and_classification.title",
  titleDefault: "Build an elemental cost plan",
  descKey: "cases.elemental_cost_plan_and_classification.desc",
  descDefault:
    "Structure a cost plan by classified element rather than by trade, check it against the classification rules, and issue a plan a designer can actually work to.",
  estMinutes: 11,
  steps: [
    {
      id: "structure",
      icon: "Table2",
      inputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.structure.in.design",
          label: "Scheme design",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.structure.in.standard",
          label: "Element classification",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.structure.out.bill",
          label: "Element-structured bill",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.structure.out.sections",
          label: "Coded plan sections",
        },
      ],
      titleKey:
        "cases.elemental_cost_plan_and_classification.step.structure.title",
      titleDefault: "Structure the plan by element",
      whatKey:
        "cases.elemental_cost_plan_and_classification.step.structure.what",
      whatDefault:
        "Lay out the bill by classified element, substructure, frame, envelope, internal finishes, services, rather than by trade, and tag each section with its classification code.",
      whyKey: "cases.elemental_cost_plan_and_classification.step.structure.why",
      whyDefault:
        "A design team reads a cost plan element by element, not trade by trade. Structuring it that way from the outset is what makes the plan legible to the people who have to design against it.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "classify",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.classify.in.plan",
          label: "Element-structured plan",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.classify.in.rules",
          label: "Classification rule set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.classify.out.report",
          label: "Structure check report",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.classify.out.clean",
          label: "Fully classified plan",
        },
      ],
      titleKey:
        "cases.elemental_cost_plan_and_classification.step.classify.title",
      titleDefault: "Check the classification rules",
      whatKey:
        "cases.elemental_cost_plan_and_classification.step.classify.what",
      whatDefault:
        "Run the structure rules across the plan and confirm every section carries the classification code the standard expects, with nothing left in an unclassified catch-all.",
      whyKey: "cases.elemental_cost_plan_and_classification.step.classify.why",
      whyDefault:
        "A cost plan that will not map cleanly to the classification standard cannot be compared to a benchmark or handed to a quantity surveyor on the other side of the table.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "issue",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.issue.in.plan",
          label: "Validated cost plan",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.issue.in.totals",
          label: "Element cost totals",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.issue.out.report",
          label: "Elemental cost report",
        },
        {
          labelKey:
            "cases.elemental_cost_plan_and_classification.step.issue.out.budget",
          label: "Design-ready budget",
        },
      ],
      titleKey: "cases.elemental_cost_plan_and_classification.step.issue.title",
      titleDefault: "Issue the elemental report",
      whatKey: "cases.elemental_cost_plan_and_classification.step.issue.what",
      whatDefault:
        "Export the cost plan broken down by element with its classification code, ready for the design team to work against and the client to approve.",
      whyKey: "cases.elemental_cost_plan_and_classification.step.issue.why",
      whyDefault:
        "An elemental report is the one document that lets a designer see exactly where the budget sits and where a design decision will move it.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
