// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Appraise a development scheme".
//
// Work out what a site is worth to a developer: set the scheme mix and areas,
// price the build from benchmarks, and let the residual land value and
// viability fall out the other end.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "appraise-a-development-scheme",
  order: 342,
  category: "estimating",
  companyTypes: ["developer-client", "cost-consultant"],
  icon: "Building2",
  titleKey: "cases.appraise_a_development_scheme.title",
  titleDefault: "Appraise a development scheme",
  descKey: "cases.appraise_a_development_scheme.desc",
  descDefault:
    "Work out what a site is worth to a developer: set the scheme mix and areas, price the build from benchmarks, and let the residual land value and viability fall out the other end.",
  estMinutes: 9,
  steps: [
    {
      id: "scheme",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.appraise_a_development_scheme.step.scheme.in.site",
          label: "Site parameters",
        },
        {
          labelKey: "cases.appraise_a_development_scheme.step.scheme.in.brief",
          label: "Scheme brief",
        },
        {
          labelKey: "cases.appraise_a_development_scheme.step.scheme.in.market",
          label: "Market values",
        },
      ],
      outputs: [
        {
          labelKey: "cases.appraise_a_development_scheme.step.scheme.out.mix",
          label: "Scheme mix and areas",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.scheme.out.revenue",
          label: "Revenue assumptions",
        },
      ],
      titleKey: "cases.appraise_a_development_scheme.step.scheme.title",
      titleDefault: "Set the scheme and assumptions",
      whatKey: "cases.appraise_a_development_scheme.step.scheme.what",
      whatDefault:
        "Lay out the scheme, the mix of uses, the unit count and the gross and net areas, then set the revenue assumptions, sales values or rents and the yield. This is the top line of the appraisal.",
      whyKey: "cases.appraise_a_development_scheme.step.scheme.why",
      whyDefault:
        "The land value is only ever as good as the scheme behind it. Getting the mix and the areas right is what separates a real appraisal from a number pulled off a comparable.",
      moduleLabel: "Property development",
      moduleLabelKey: "nav.property_dev",
      to: "/property-dev",
    },
    {
      id: "benchmark",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.benchmark.in.areas",
          label: "Scheme areas",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.benchmark.in.benchmarks",
          label: "Cost benchmarks",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.benchmark.in.allowances",
          label: "Fee and finance allowances",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.benchmark.out.build",
          label: "Build cost estimate",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.benchmark.out.total",
          label: "Total development cost",
        },
      ],
      titleKey: "cases.appraise_a_development_scheme.step.benchmark.title",
      titleDefault: "Price the build from benchmarks",
      whatKey: "cases.appraise_a_development_scheme.step.benchmark.what",
      whatDefault:
        "Pull cost-per-square-metre benchmarks for each use in the scheme and lay in the build cost, along with the usual allowances for externals, fees and finance. No drawings are needed at this stage.",
      whyKey: "cases.appraise_a_development_scheme.step.benchmark.why",
      whyDefault:
        "Build cost is the biggest number you can still influence at appraisal. A benchmark drawn from real projects keeps it honest and stops an optimistic land bid built on a soft cost.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "residual",
      icon: "Scale",
      inputs: [
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.residual.in.revenue",
          label: "Revenue assumptions",
        },
        {
          labelKey: "cases.appraise_a_development_scheme.step.residual.in.cost",
          label: "Development cost",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.residual.in.return",
          label: "Target return",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.residual.out.residual",
          label: "Residual land value",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.residual.out.viability",
          label: "Profit and viability",
        },
        {
          labelKey:
            "cases.appraise_a_development_scheme.step.residual.out.sensitivity",
          label: "Sensitivity range",
        },
      ],
      titleKey: "cases.appraise_a_development_scheme.step.residual.title",
      titleDefault: "Produce the residual land value",
      whatKey: "cases.appraise_a_development_scheme.step.residual.what",
      whatDefault:
        "Run the appraisal to its residual land value, the most you can pay for the site and still hit your return, and read off the viability and profit on cost. Flex the key assumptions to see how tight it is.",
      whyKey: "cases.appraise_a_development_scheme.step.residual.why",
      whyDefault:
        "The residual is the number the whole exercise exists to produce, the most you can bid and still make the scheme work. Seeing how far it moves on a small change in cost or value tells you how much risk you are carrying.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
