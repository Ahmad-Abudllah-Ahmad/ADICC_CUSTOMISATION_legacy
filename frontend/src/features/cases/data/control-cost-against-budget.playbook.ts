// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Control cost against budget".
//
// Hold the job to its budget: set the priced bill as the baseline, track
// committed and actual spend against it, then report the variance early enough
// to steer. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "control-cost-against-budget",
  order: 160,
  category: "commercial",
  companyTypes: ["general-contractor", "cost-consultant", "project-manager"],
  icon: "Scale",
  titleKey: "cases.control_cost_against_budget.title",
  titleDefault: "Control cost against budget",
  descKey: "cases.control_cost_against_budget.desc",
  descDefault:
    "Hold the job to its number: fix the priced bill as the budget baseline, track committed and actual spend against it trade by trade, and report the variance while there is still time to act.",
  estMinutes: 12,
  steps: [
    {
      id: "baseline",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.control_cost_against_budget.step.baseline.in.bill",
          label: "Agreed priced bill",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.baseline.in.codes",
          label: "Cost code structure",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.control_cost_against_budget.step.baseline.out.baseline",
          label: "Fixed budget baseline",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.baseline.out.lines",
          label: "Budget lines by trade",
        },
      ],
      titleKey: "cases.control_cost_against_budget.step.baseline.title",
      titleDefault: "Set the budget baseline",
      whatKey: "cases.control_cost_against_budget.step.baseline.what",
      whatDefault:
        "Take the agreed priced bill and fix it as the cost budget, broken down by trade or cost code, so every later commitment and invoice has a target line to be measured against.",
      whyKey: "cases.control_cost_against_budget.step.baseline.why",
      whyDefault:
        "You cannot control spend without a fixed line to control it against, and a budget that keeps drifting hides overruns as fast as they appear. Locking the baseline is what makes a variance mean something.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
    {
      id: "track",
      icon: "Banknote",
      inputs: [
        {
          labelKey: "cases.control_cost_against_budget.step.track.in.baseline",
          label: "Budget baseline",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.track.in.orders",
          label: "Orders and subcontracts",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.track.in.invoices",
          label: "Invoices and site records",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.control_cost_against_budget.step.track.out.committed",
          label: "Committed cost",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.track.out.actual",
          label: "Actual cost",
        },
      ],
      titleKey: "cases.control_cost_against_budget.step.track.title",
      titleDefault: "Track committed and actual",
      whatKey: "cases.control_cost_against_budget.step.track.what",
      whatDefault:
        "Book orders and subcontracts as committed cost and invoices and site records as actual cost, each against its budget line, so you can see budget, committed and spent side by side.",
      whyKey: "cases.control_cost_against_budget.step.track.why",
      whyDefault:
        "Committed cost is the overrun you have already signed for but not yet paid, and it is where jobs quietly go over before a single invoice arrives. Tracking it, not just actuals, is what gives you real warning.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "variance",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.control_cost_against_budget.step.variance.in.budget",
          label: "Budget baseline",
        },
        {
          labelKey: "cases.control_cost_against_budget.step.variance.in.spend",
          label: "Committed and actual cost",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.control_cost_against_budget.step.variance.out.report",
          label: "Cost variance report",
        },
        {
          labelKey:
            "cases.control_cost_against_budget.step.variance.out.forecast",
          label: "Forecast final cost",
        },
      ],
      titleKey: "cases.control_cost_against_budget.step.variance.title",
      titleDefault: "Report the variance",
      whatKey: "cases.control_cost_against_budget.step.variance.what",
      whatDefault:
        "Produce the cost report showing budget against committed and actual with the forecast final cost per trade, and flag the lines trending over so the team can act on them by name.",
      whyKey: "cases.control_cost_against_budget.step.variance.why",
      whyDefault:
        "An overrun caught in month four can still be steered by reworking scope or renegotiating; the same number found at final account is only a loss to explain. Reporting variance early is the entire point of cost control.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
