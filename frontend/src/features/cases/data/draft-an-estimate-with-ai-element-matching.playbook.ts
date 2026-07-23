// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Draft an estimate with AI element matching".
//
// Build a first-pass estimate fast: match imported elements to cost items, let
// the AI estimator propose priced lines the estimator confirms, accept them
// into the bill and validate the result before you trust the number.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "draft-an-estimate-with-ai-element-matching",
  order: 304,
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "Sparkles",
  titleKey: "cases.draft_an_estimate_with_ai_element_matching.title",
  titleDefault: "Draft an estimate with AI element matching",
  descKey: "cases.draft_an_estimate_with_ai_element_matching.desc",
  descDefault:
    "Match imported elements to cost items, let AI price the scope, accept it into the bill and validate before you trust it.",
  estMinutes: 10,
  steps: [
    {
      id: "match",
      icon: "Combine",
      inputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.match.in.elements",
          label: "Imported elements",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.match.in.catalog",
          label: "Cost database",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.match.in.descriptions",
          label: "Element descriptions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.match.out.matches",
          label: "Matched cost items",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.match.out.scores",
          label: "Confidence scores",
        },
      ],
      titleKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.match.title",
      titleDefault: "Match elements to cost items",
      whatKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.match.what",
      whatDefault:
        "Import your elements and descriptions and let the matcher line each one up to a cost-database item, with a confidence score on every match.",
      whyKey: "cases.draft_an_estimate_with_ai_element_matching.step.match.why",
      whyDefault:
        "Coding hundreds of lines by hand is slow and uneven. Scored matches show where to trust the machine and where to check by hand.",
      moduleLabel: "Match Elements",
      to: "/match-elements",
    },
    {
      id: "ai-price",
      icon: "Sparkles",
      inputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.in.scope",
          label: "Matched scope",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.in.rates",
          label: "Rate references",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.out.lines",
          label: "Proposed priced lines",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.out.confirmed",
          label: "Confirmed prices",
        },
      ],
      titleKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.title",
      titleDefault: "Let AI price the scope",
      whatKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.what",
      whatDefault:
        "Run the AI estimator over the matched scope so it proposes priced lines, then confirm or overrule each suggestion.",
      whyKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.ai-price.why",
      whyDefault:
        "A first-pass priced draft in minutes saves hours, but a number only goes in the bid once a person has signed it off.",
      moduleLabel: "AI Estimator",
      to: "/ai-estimator",
    },
    {
      id: "accept-boq",
      icon: "Table2",
      inputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.in.lines",
          label: "Confirmed priced lines",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.in.quantities",
          label: "Measured quantities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.out.boq",
          label: "Draft bill of quantities",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.out.total",
          label: "Priced total",
        },
      ],
      titleKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.title",
      titleDefault: "Accept lines into the bill",
      whatKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.what",
      whatDefault:
        "Pull the confirmed lines into the bill of quantities and enter or adjust the quantities.",
      whyKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.why",
      whyDefault:
        "The bill is what you actually price and submit. Getting the quantities right here is where the money is won or lost.",
      moduleLabel: "BOQ",
      to: "/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.validate.in.boq",
          label: "Draft bill",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.validate.in.rules",
          label: "Quality rule set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.validate.out.report",
          label: "Validation report",
        },
        {
          labelKey:
            "cases.draft_an_estimate_with_ai_element_matching.step.validate.out.flags",
          label: "Flagged issues",
        },
      ],
      titleKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.validate.title",
      titleDefault: "Validate before you trust it",
      whatKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.validate.what",
      whatDefault:
        "Run validation over the finished bill to flag zero prices, missing quantities, duplicates and rate outliers.",
      whyKey:
        "cases.draft_an_estimate_with_ai_element_matching.step.validate.why",
      whyDefault:
        "An AI draft can leave a hole or a silly rate that reads fine at a glance. Catching it before submission stops an underpriced or embarrassing bid.",
      moduleLabel: "Validation",
      to: "/validation",
    },
  ],
};

export default playbook;
