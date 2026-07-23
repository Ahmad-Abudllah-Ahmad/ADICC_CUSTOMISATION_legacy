// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Draft the first year maintenance budget".
//
// Put a real number on running the building: list the assets to maintain, price
// their planned and reactive work from cost data, and report a first-year budget.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "draft-the-first-year-maintenance-budget",
  order: 292,
  category: "handover",
  companyTypes: ["owner-operator", "developer-client"],
  stage: "operate",
  icon: "Calculator",
  titleKey: "cases.draft_the_first_year_maintenance_budget.title",
  titleDefault: "Draft the first year maintenance budget",
  descKey: "cases.draft_the_first_year_maintenance_budget.desc",
  descDefault:
    "Put a real number on running the building: list the assets to maintain, price their planned and reactive work from cost data, and report a first-year budget you can defend.",
  longDescKey: "cases.draft_the_first_year_maintenance_budget.longdesc",
  longDescDefault:
    "An operator who takes on a building without a maintenance budget is one who runs out of money halfway through the year. This case lists the assets that need care, prices their planned service and a sensible reactive allowance from real cost data, and reports a first-year budget broken down by asset and month so the number holds up when finance asks where it came from.",
  estMinutes: 9,
  steps: [
    {
      id: "assets",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.assets.in.register",
          label: "Asset register",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.assets.in.requirements",
          label: "Maintenance requirements",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.assets.out.list",
          label: "Maintainable asset list",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.assets.out.frequencies",
          label: "Service frequencies",
        },
      ],
      titleKey: "cases.draft_the_first_year_maintenance_budget.step.assets.title",
      titleDefault: "List the assets to maintain",
      whatKey: "cases.draft_the_first_year_maintenance_budget.step.assets.what",
      whatDefault:
        "Pull the assets that carry a maintenance cost from the register, note the planned service each one needs and how often, and flag the ones whose failure would need a reactive allowance too.",
      whyKey: "cases.draft_the_first_year_maintenance_budget.step.assets.why",
      whyDefault:
        "A budget built without the asset list is a guess. Starting from what you actually have to maintain is what makes the number defensible rather than a finger in the air.",
      moduleLabel: "Assets",
      moduleLabelKey: "nav.assets",
      to: "/assets",
    },
    {
      id: "rates",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.rates.in.list",
          label: "Maintainable asset list",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.rates.in.rates",
          label: "Maintenance cost rates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.rates.out.planned",
          label: "Planned maintenance cost",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.rates.out.reactive",
          label: "Reactive allowance",
        },
      ],
      titleKey: "cases.draft_the_first_year_maintenance_budget.step.rates.title",
      titleDefault: "Price the work from cost data",
      whatKey: "cases.draft_the_first_year_maintenance_budget.step.rates.what",
      whatDefault:
        "Price the planned service tasks from cost data, add a reactive allowance sized to the age and criticality of the assets, and build up the yearly cost line by line instead of as a round guess.",
      whyKey: "cases.draft_the_first_year_maintenance_budget.step.rates.why",
      whyDefault:
        "A maintenance budget pulled from thin air is the one that blows in month three. Pricing it off real rates, planned plus a reasoned reactive allowance, is what makes it survive contact with the real year.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "budget",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.budget.in.planned",
          label: "Planned maintenance cost",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.budget.in.reactive",
          label: "Reactive allowance",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.budget.out.budget",
          label: "First-year maintenance budget",
        },
        {
          labelKey:
            "cases.draft_the_first_year_maintenance_budget.step.budget.out.profile",
          label: "Monthly cash profile",
        },
      ],
      titleKey: "cases.draft_the_first_year_maintenance_budget.step.budget.title",
      titleDefault: "Report the first-year budget",
      whatKey: "cases.draft_the_first_year_maintenance_budget.step.budget.what",
      whatDefault:
        "Report the budget broken down by asset and by month, separating planned from reactive, so finance can see what drives it and when the cash actually falls across the year.",
      whyKey: "cases.draft_the_first_year_maintenance_budget.step.budget.why",
      whyDefault:
        "A single lump-sum budget tells finance nothing and defends nothing. Breaking it down by asset and month is what gets it approved and lets you track spend against it as the year runs.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
