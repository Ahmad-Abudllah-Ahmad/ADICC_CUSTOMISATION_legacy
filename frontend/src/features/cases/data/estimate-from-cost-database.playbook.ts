// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Estimate from a cost database".
//
// Price a job from a real cost database: find the right items, build the BOQ,
// bundle repeat work into assemblies, then validate before you commit a number.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "estimate-from-cost-database",
  order: 75,
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "Database",
  titleKey: "cases.estimate_from_cost_database.title",
  titleDefault: "Estimate from a cost database",
  descKey: "cases.estimate_from_cost_database.desc",
  descDefault:
    "Pull priced items from a real cost database, build the bill from them, bundle recurring build-ups into assemblies and run the checks before you commit to a tender figure.",
  estMinutes: 12,
  steps: [
    {
      id: "browse",
      icon: "Database",
      inputs: [
        {
          labelKey: "cases.estimate_from_cost_database.step.browse.in.database",
          label: "Cost database",
        },
        {
          labelKey: "cases.estimate_from_cost_database.step.browse.in.scope",
          label: "Work to price",
        },
        {
          labelKey: "cases.estimate_from_cost_database.step.browse.in.search",
          label: "Trade & keywords",
        },
      ],
      outputs: [
        {
          labelKey: "cases.estimate_from_cost_database.step.browse.out.items",
          label: "Selected priced items",
        },
        {
          labelKey: "cases.estimate_from_cost_database.step.browse.out.rates",
          label: "Verified unit rates",
        },
      ],
      titleKey: "cases.estimate_from_cost_database.step.browse.title",
      titleDefault: "Find the right priced items",
      whatKey: "cases.estimate_from_cost_database.step.browse.what",
      whatDefault:
        "Search the database by trade, keyword or classification code, then read the item description and inclusions before you pull the rate in. Check the unit and what labour, material and plant the rate is built from.",
      whyKey: "cases.estimate_from_cost_database.step.browse.why",
      whyDefault:
        "A rate is only correct if its scope matches the work in front of you. Reading the item first stops you pricing a labour-only fix line as full supply and fix, a mismatch that can double or halve a whole trade.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "build",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.estimate_from_cost_database.step.build.in.items",
          label: "Selected priced items",
        },
        {
          labelKey:
            "cases.estimate_from_cost_database.step.build.in.quantities",
          label: "Measured quantities",
        },
      ],
      outputs: [
        {
          labelKey: "cases.estimate_from_cost_database.step.build.out.boq",
          label: "Structured BOQ",
        },
        {
          labelKey: "cases.estimate_from_cost_database.step.build.out.totals",
          label: "Live section totals",
        },
      ],
      titleKey: "cases.estimate_from_cost_database.step.build.title",
      titleDefault: "Build the BOQ",
      whatKey: "cases.estimate_from_cost_database.step.build.what",
      whatDefault:
        "Place the chosen items into the bill, enter your quantities and let the line and section totals roll up live. Order the sections the way you intend to report and tender them, by trade or by element.",
      whyKey: "cases.estimate_from_cost_database.step.build.why",
      whyDefault:
        "The bill is where scope turns into money, so its structure has to survive scrutiny. Starting each line from a database item means it already carries a traceable source and a rate you can justify, rather than a number typed from memory.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
    {
      id: "assemblies",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.estimate_from_cost_database.step.assemblies.in.lines",
          label: "Repeated build-ups",
        },
        {
          labelKey:
            "cases.estimate_from_cost_database.step.assemblies.in.components",
          label: "Component rates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.estimate_from_cost_database.step.assemblies.out.assembly",
          label: "Reusable assembly",
        },
        {
          labelKey:
            "cases.estimate_from_cost_database.step.assemblies.out.consistent",
          label: "Consistent pricing",
        },
      ],
      titleKey: "cases.estimate_from_cost_database.step.assemblies.title",
      titleDefault: "Bundle repeat work into assemblies",
      whatKey: "cases.estimate_from_cost_database.step.assemblies.what",
      whatDefault:
        "Bundle a recurring build-up, such as a concrete wall with its formwork and reinforcement, into one assembly, so entering a single square metre quantity drives concrete, shutter and steel together in the right proportions.",
      whyKey: "cases.estimate_from_cost_database.step.assemblies.why",
      whyDefault:
        "Assemblies keep repeated pricing both fast and consistent across a big bill. Adjust a component rate once and every line built on that assembly moves with it, so a steel price rise cannot be applied in one place and forgotten in ten others.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.estimate_from_cost_database.step.validate.in.estimate",
          label: "Finished estimate",
        },
        {
          labelKey:
            "cases.estimate_from_cost_database.step.validate.in.benchmarks",
          label: "Benchmark bands",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.estimate_from_cost_database.step.validate.out.report",
          label: "Validation report",
        },
        {
          labelKey: "cases.estimate_from_cost_database.step.validate.out.flags",
          label: "Flagged errors",
        },
      ],
      titleKey: "cases.estimate_from_cost_database.step.validate.title",
      titleDefault: "Validate before you commit",
      whatKey: "cases.estimate_from_cost_database.step.validate.what",
      whatDefault:
        "Put the finished estimate through the checks for zero prices, blank quantities, duplicated positions and unit rates sitting well outside the benchmark band for that item.",
      whyKey: "cases.estimate_from_cost_database.step.validate.why",
      whyDefault:
        "One blank quantity or a stray zero in a big rate can move a tender by a serious sum, and it is always found the day after submission. Validation surfaces those honest slips while you can still fix them privately.",
      moduleLabel: "Validation",
      moduleLabelKey: "nav.validation",
      to: "/validation",
    },
  ],
};

export default playbook;
