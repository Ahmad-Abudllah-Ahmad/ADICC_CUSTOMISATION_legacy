// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run the cost-value reconciliation".
//
// Set the cost you have committed against the value you have earned to the
// same date, and read the real margin before it is too late to defend it.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "cost-value-reconciliation",
  order: 180,
  category: "commercial",
  companyTypes: ["general-contractor", "cost-consultant", "project-manager"],
  icon: "Scale",
  titleKey: "cases.cost_value_reconciliation.title",
  titleDefault: "Run the cost-value reconciliation",
  descKey: "cases.cost_value_reconciliation.desc",
  descDefault:
    "Set the cost you have committed against the value you have earned to the same cut-off date, and read the true margin each period while there is still time to act on it.",
  estMinutes: 12,
  steps: [
    {
      id: "cost",
      icon: "Banknote",
      inputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.cost.in.payments",
          label: "Certified payments",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.cost.in.commitments",
          label: "Placed orders",
        },
      ],
      outputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.cost.out.cost",
          label: "Committed cost to date",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.cost.out.accruals",
          label: "Accruals included",
        },
      ],
      titleKey: "cases.cost_value_reconciliation.step.cost.title",
      titleDefault: "Pull the committed cost",
      whatKey: "cases.cost_value_reconciliation.step.cost.what",
      whatDefault:
        "Total the cost to the cut-off date: certified subcontractor payments, materials, plant, labour and the orders placed but not yet invoiced, so accruals are in and nothing real is left out.",
      whyKey: "cases.cost_value_reconciliation.step.cost.why",
      whyDefault:
        "Cost that has been committed but not yet invoiced is the trap that makes a job look healthy right up until the bills arrive. Bringing accruals in now is what stops the margin lurching the wrong way next month.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "value",
      icon: "TrendingUp",
      inputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.value.in.progress",
          label: "Work in place",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.value.in.variations",
          label: "Agreed variations",
        },
      ],
      outputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.value.out.value",
          label: "Earned value to date",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.value.out.wip",
          label: "Work in progress",
        },
      ],
      titleKey: "cases.cost_value_reconciliation.step.value.title",
      titleDefault: "Value the work earned",
      whatKey: "cases.cost_value_reconciliation.step.value.what",
      whatDefault:
        "Value the work genuinely put in place to that same date, add agreed variations and any work in progress, and be honest about over-claiming that will have to be given back later.",
      whyKey: "cases.cost_value_reconciliation.step.value.why",
      whyDefault:
        "Cost and value only tell the truth when they are cut on the exact same date. Value the work straight, and the margin you read is one you can stand behind, not a number you have to explain away.",
      moduleLabel: "Value",
      moduleLabelKey: "nav.value",
      to: "/projects/:projectId/value",
    },
    {
      id: "margin",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.margin.in.cost",
          label: "Committed cost",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.margin.in.value",
          label: "Earned value",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.margin.in.allowance",
          label: "Tender allowance",
        },
      ],
      outputs: [
        {
          labelKey: "cases.cost_value_reconciliation.step.margin.out.margin",
          label: "Period margin",
        },
        {
          labelKey: "cases.cost_value_reconciliation.step.margin.out.actions",
          label: "Actions by element",
        },
      ],
      titleKey: "cases.cost_value_reconciliation.step.margin.title",
      titleDefault: "Read the margin and act",
      whatKey: "cases.cost_value_reconciliation.step.margin.what",
      whatDefault:
        "Subtract cost from value to show the margin this period, compare it against the tender allowance, and trace any drop back to the trade or element that caused it so you know exactly where to act.",
      whyKey: "cases.cost_value_reconciliation.step.margin.why",
      whyDefault:
        "A margin that is quietly slipping is recoverable in month three and terminal in month nine. Catching the slide early, against the element that caused it, is the difference between a fix and a loss.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
