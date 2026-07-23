// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Sense-check an estimate against benchmarks".
//
// Take a priced estimate, hold it up against the reference cost base and your
// own history, and catch the rates that are plainly wrong before it goes out.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "sense-check-an-estimate-with-benchmarks",
  order: 195,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "developer-client"],
  icon: "Scale",
  titleKey: "cases.sense_check_an_estimate_with_benchmarks.title",
  titleDefault: "Sense-check an estimate against benchmarks",
  descKey: "cases.sense_check_an_estimate_with_benchmarks.desc",
  descDefault:
    "Hold a priced estimate up against the reference cost base and your own history, flag the rates and the cost per square metre that look wrong, and fix them before the number leaves the building.",
  estMinutes: 10,
  steps: [
    {
      id: "open",
      icon: "FileSpreadsheet",
      inputs: [
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.open.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.open.in.area",
          label: "Floor area",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.open.out.breakdown",
          label: "Cost breakdown",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.open.out.persqm",
          label: "Cost per square metre",
        },
      ],
      titleKey: "cases.sense_check_an_estimate_with_benchmarks.step.open.title",
      titleDefault: "Open the priced estimate",
      whatKey: "cases.sense_check_an_estimate_with_benchmarks.step.open.what",
      whatDefault:
        "Pull up the priced BOQ and read the shape of it: the total, the split by element or trade, and the cost per square metre of floor area, so you know what a benchmark should be measured against.",
      whyKey: "cases.sense_check_an_estimate_with_benchmarks.step.open.why",
      whyDefault:
        "You cannot judge whether a number is sensible until you can see how it breaks down. Getting the totals and the rate per square metre in front of you is the ground every later check stands on.",
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
            "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.in.rates",
          label: "Estimate rates",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.in.costbase",
          label: "Reference cost base",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.out.comparison",
          label: "Rates vs market band",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.out.outliers",
          label: "Off-band rates",
        },
      ],
      titleKey:
        "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.title",
      titleDefault: "Compare against the cost base",
      whatKey:
        "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.what",
      whatDefault:
        "Take the big-value and the odd-looking rates into the cost base and set them beside the reference prices for the same work and region, noting anything sitting well above or below the market band.",
      whyKey:
        "cases.sense_check_an_estimate_with_benchmarks.step.benchmark.why",
      whyDefault:
        "A rate ten times too high wins you nothing and a rate ten times too low wins you a job you lose money on. Comparing against a real cost base is how a keyed-in slip gets caught before it becomes a bid.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "flag",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.flag.in.outliers",
          label: "Flagged outliers",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.flag.in.estimate",
          label: "Priced estimate",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.flag.out.resolved",
          label: "Flags resolved",
        },
        {
          labelKey:
            "cases.sense_check_an_estimate_with_benchmarks.step.flag.out.clean",
          label: "Checked estimate",
        },
      ],
      titleKey: "cases.sense_check_an_estimate_with_benchmarks.step.flag.title",
      titleDefault: "Flag and fix the outliers",
      whatKey: "cases.sense_check_an_estimate_with_benchmarks.step.flag.what",
      whatDefault:
        "Run the estimate through the checks for zero prices, missing quantities and rates outside a sensible band, then correct or explain every flag so nothing unexplained survives into the issued number.",
      whyKey: "cases.sense_check_an_estimate_with_benchmarks.step.flag.why",
      whyDefault:
        "One fat-fingered rate can swing a tender by a fortune and cost you the job or the margin. A clean pass through the checks is the last gate before the estimate becomes a commitment.",
      moduleLabel: "Validation",
      moduleLabelKey: "nav.validation",
      to: "/validation",
    },
  ],
};

export default playbook;
