// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Value engineer a design to the target cost".
//
// Bring an over-budget design back to target without gutting it: find the
// costliest elements, test cheaper options for value, and report the savings.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "value-engineer-a-design-to-the-target-cost",
  order: 286,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "developer-client"],
  icon: "TrendingUp",
  titleKey: "cases.value_engineer_a_design_to_the_target_cost.title",
  titleDefault: "Value engineer a design to the target cost",
  descKey: "cases.value_engineer_a_design_to_the_target_cost.desc",
  descDefault:
    "Bring an over-budget design back to target without gutting it: find the costliest elements in the bill, test cheaper options for their value, and report the savings you can defend.",
  longDescKey: "cases.value_engineer_a_design_to_the_target_cost.longdesc",
  longDescDefault:
    "Value engineering done with a blunt knife strips out the things that made the design worth building. This case finds where the money actually sits in the bill, tests substitutions and design changes for what they save against what they cost the scheme, and reports only the savings you can stand behind so the design hits its target with its value intact.",
  estMinutes: 10,
  steps: [
    {
      id: "baseline",
      icon: "Table2",
      inputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.baseline.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.baseline.in.target",
          label: "Cost target",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.baseline.out.hotspots",
          label: "Cost hotspots",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.baseline.out.gap",
          label: "Savings gap",
        },
      ],
      titleKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.baseline.title",
      titleDefault: "Find where the money sits",
      whatKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.baseline.what",
      whatDefault:
        "Sort the priced bill to see which elements carry the cost and how far the total sits above the target, so the value-engineering effort goes where the money actually is.",
      whyKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.baseline.why",
      whyDefault:
        "Chasing pennies across cheap lines while the expensive elements go untouched is wasted effort. Finding the hotspots first is what points value engineering at the few changes that can actually close the gap.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "options",
      icon: "LineChart",
      inputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.options.in.hotspots",
          label: "Cost hotspots",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.options.in.alternatives",
          label: "Alternative specs",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.options.out.scored",
          label: "Scored options",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.options.out.recommended",
          label: "Recommended changes",
        },
      ],
      titleKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.options.title",
      titleDefault: "Test the options for value",
      whatKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.options.what",
      whatDefault:
        "For each hotspot, test the cheaper alternatives, weigh what each one saves against what it costs the scheme in quality, programme or running cost, and keep the ones that pay their way.",
      whyKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.options.why",
      whyDefault:
        "A saving that wrecks the maintenance cost or the look of the building is not a saving. Scoring options on value, not just first cost, is what stops value engineering turning into value destruction.",
      moduleLabel: "Value",
      moduleLabelKey: "nav.value",
      to: "/projects/:projectId/value",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.report.in.recommended",
          label: "Recommended changes",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.report.in.target",
          label: "Cost target",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.report.out.report",
          label: "Value engineering report",
        },
        {
          labelKey:
            "cases.value_engineer_a_design_to_the_target_cost.step.report.out.plan",
          label: "Revised cost plan",
        },
      ],
      titleKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.report.title",
      titleDefault: "Report the defensible savings",
      whatKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.report.what",
      whatDefault:
        "Report the changes you recommend with the saving and the trade-off spelled out for each, and show the revised total against target, so the client decides on evidence rather than a bare number.",
      whyKey:
        "cases.value_engineer_a_design_to_the_target_cost.step.report.why",
      whyDefault:
        "A savings list with no trade-offs shown is one the client cannot make a real decision on. Laying out what each change costs as well as saves is what gets value engineering approved instead of argued over.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
