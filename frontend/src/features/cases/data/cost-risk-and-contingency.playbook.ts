// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set contingency from cost risk".
//
// Turn a single-point estimate into a range: run a Monte Carlo over the risky
// items, read the P50 to P90 spread and set a contingency you can defend.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "cost-risk-and-contingency",
  order: 80,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "developer-client"],
  icon: "Dice5",
  titleKey: "cases.cost_risk_and_contingency.title",
  titleDefault: "Set contingency from cost risk",
  descKey: "cases.cost_risk_and_contingency.desc",
  descDefault:
    "Turn a single-point estimate into a range, run a Monte Carlo over the genuinely uncertain lines, read the P50 to P90 spread and set a contingency you can defend line by line.",
  estMinutes: 11,
  steps: [
    {
      id: "baseline",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.cost_risk_and_contingency.step.baseline.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey:
            "cases.cost_risk_and_contingency.step.baseline.in.validation",
          label: "Validation report",
        },
      ],
      outputs: [
        {
          labelKey: "cases.cost_risk_and_contingency.step.baseline.out.base",
          label: "Verified base estimate",
        },
        {
          labelKey:
            "cases.cost_risk_and_contingency.step.baseline.out.uncertain",
          label: "Uncertain lines marked",
        },
      ],
      titleKey: "cases.cost_risk_and_contingency.step.baseline.title",
      titleDefault: "Fix the base estimate",
      whatKey: "cases.cost_risk_and_contingency.step.baseline.what",
      whatDefault:
        "Check the bill is complete and fully priced first, then mark the handful of lines that are genuinely uncertain, whether in quantity, in rate or in ground conditions you cannot yet see.",
      whyKey: "cases.cost_risk_and_contingency.step.baseline.why",
      whyDefault:
        "Running risk over a bill with gaps or errors just dresses that error up in a confident looking curve. A clean, complete base estimate is the only thing that makes the resulting range worth trusting.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
    {
      id: "simulate",
      icon: "Dice5",
      inputs: [
        {
          labelKey:
            "cases.cost_risk_and_contingency.step.simulate.in.uncertain",
          label: "Uncertain lines",
        },
        {
          labelKey: "cases.cost_risk_and_contingency.step.simulate.in.ranges",
          label: "Three-point ranges",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.cost_risk_and_contingency.step.simulate.out.distribution",
          label: "Cost distribution",
        },
        {
          labelKey: "cases.cost_risk_and_contingency.step.simulate.out.curve",
          label: "P50 to P90 curve",
        },
      ],
      titleKey: "cases.cost_risk_and_contingency.step.simulate.title",
      titleDefault: "Run the Monte Carlo",
      whatKey: "cases.cost_risk_and_contingency.step.simulate.what",
      whatDefault:
        "Give each uncertain line a low, most likely and high value, link the ones that move together such as fuel and haulage, then run the simulation across thousands of iterations to build a cost distribution.",
      whyKey: "cases.cost_risk_and_contingency.step.simulate.why",
      whyDefault:
        "A single headline figure hides how much the outturn could swing. The P50 to P90 curve tells you plainly how much cover you need to carry to hit a confidence level you are willing to sign up to.",
      moduleLabel: "Cost risk",
      moduleLabelKey: "nav.risks",
      to: "/risks?tab=montecarlo",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.cost_risk_and_contingency.step.report.in.curve",
          label: "Cost S-curve",
        },
        {
          labelKey: "cases.cost_risk_and_contingency.step.report.in.confidence",
          label: "Chosen confidence level",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.cost_risk_and_contingency.step.report.out.contingency",
          label: "Contingency figure",
        },
        {
          labelKey: "cases.cost_risk_and_contingency.step.report.out.tornado",
          label: "Tornado chart",
        },
      ],
      titleKey: "cases.cost_risk_and_contingency.step.report.title",
      titleDefault: "Set contingency and report it",
      whatKey: "cases.cost_risk_and_contingency.step.report.what",
      whatDefault:
        "Choose the confidence level the job warrants, read the contingency that point on the S-curve implies and export the tornado chart that ranks the biggest drivers of the spread.",
      whyKey: "cases.cost_risk_and_contingency.step.report.why",
      whyDefault:
        "A contingency drawn from a distribution holds up in front of a board or a client in a way that a flat ten percent never does. The tornado shows exactly which risks the money is set aside for, so the number reads as reasoned rather than padded.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
