// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Localize an estimate to a region".
//
// Move a priced estimate to another region honestly: pick the regional cost
// base, apply the local rates and adjustment factors, then validate that the
// result still holds. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "localize-an-estimate-to-a-region",
  order: 140,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "developer-client"],
  icon: "Ruler",
  titleKey: "cases.localize_an_estimate_to_a_region.title",
  titleDefault: "Localize an estimate to a region",
  descKey: "cases.localize_an_estimate_to_a_region.desc",
  descDefault:
    "Move a priced estimate to another region without guessing: pick the regional cost base, apply the local rates and adjustment factors, then validate that the localized numbers still stand up.",
  estMinutes: 12,
  steps: [
    {
      id: "base",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.base.in.estimate",
          label: "Priced estimate",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.base.in.region",
          label: "Target region and currency",
        },
      ],
      outputs: [
        {
          labelKey: "cases.localize_an_estimate_to_a_region.step.base.out.base",
          label: "Regional cost base",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.base.out.coverage",
          label: "Trade coverage check",
        },
      ],
      titleKey: "cases.localize_an_estimate_to_a_region.step.base.title",
      titleDefault: "Pick the regional cost base",
      whatKey: "cases.localize_an_estimate_to_a_region.step.base.what",
      whatDefault:
        "Choose the cost base that matches the region and currency the work will be built in, and check it covers the trades in your bill rather than leaving gaps you would have to price by hand.",
      whyKey: "cases.localize_an_estimate_to_a_region.step.base.why",
      whyDefault:
        "Labour rates, material prices and productivity differ sharply from one region to the next, so a rate that was right in one place can be far out in another. Starting from the local base is what keeps the estimate defensible in the new market.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "apply",
      icon: "Scale",
      inputs: [
        {
          labelKey: "cases.localize_an_estimate_to_a_region.step.apply.in.base",
          label: "Regional cost base",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.apply.in.quantities",
          label: "Original quantities",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.apply.in.factors",
          label: "Adjustment factors",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.apply.out.rerated",
          label: "Re-rated bill",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.apply.out.rates",
          label: "Localized unit rates",
        },
      ],
      titleKey: "cases.localize_an_estimate_to_a_region.step.apply.title",
      titleDefault: "Apply local rates and factors",
      whatKey: "cases.localize_an_estimate_to_a_region.step.apply.what",
      whatDefault:
        "Re-rate the bill against the regional base and apply the location and currency adjustment factors, keeping quantities as they are so only the pricing moves and the scope stays fixed.",
      whyKey: "cases.localize_an_estimate_to_a_region.step.apply.why",
      whyDefault:
        "Holding the quantities and changing only the rates keeps the two effects, scope and price, cleanly separate. That way you can see exactly how much of the new number is the region and how much is the design.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.validate.in.rerated",
          label: "Re-rated bill",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.validate.in.benchmarks",
          label: "Regional benchmarks",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.validate.out.report",
          label: "Validation report",
        },
        {
          labelKey:
            "cases.localize_an_estimate_to_a_region.step.validate.out.confirmed",
          label: "Confirmed local estimate",
        },
      ],
      titleKey: "cases.localize_an_estimate_to_a_region.step.validate.title",
      titleDefault: "Validate the localized figure",
      whatKey: "cases.localize_an_estimate_to_a_region.step.validate.what",
      whatDefault:
        "Run the localized estimate through the checks for zero prices, blank quantities and unit rates sitting outside the regional benchmark band, and review the cost per square metre against local jobs.",
      whyKey: "cases.localize_an_estimate_to_a_region.step.validate.why",
      whyDefault:
        "A currency mismatch or a factor applied twice hides easily inside a re-rated bill and can move a bid by a serious margin. Validating against local benchmarks catches the slip while you can still correct it quietly.",
      moduleLabel: "Validation",
      moduleLabelKey: "nav.validation",
      to: "/validation",
    },
  ],
};

export default playbook;
