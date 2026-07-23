// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build an assembly (recipe rate)".
//
// Turn a recurring build-up into one reusable assembly: pick the component
// items, set the factor each contributes, then drive bill lines from the single
// composite rate. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-an-assembly-recipe-rate",
  order: 135,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "subcontractor"],
  icon: "Combine",
  titleKey: "cases.build_an_assembly_recipe_rate.title",
  titleDefault: "Build an assembly (recipe rate)",
  descKey: "cases.build_an_assembly_recipe_rate.desc",
  descDefault:
    "Turn a build-up you price again and again into one reusable assembly: pick the component items, set how much of each goes in, then drive whole bill lines from a single composite rate.",
  estMinutes: 11,
  steps: [
    {
      id: "components",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.components.in.database",
          label: "Cost database",
        },
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.components.in.buildup",
          label: "Build-up scope",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.components.out.items",
          label: "Selected component items",
        },
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.components.out.rates",
          label: "Component rates and units",
        },
      ],
      titleKey: "cases.build_an_assembly_recipe_rate.step.components.title",
      titleDefault: "Pick the component items",
      whatKey: "cases.build_an_assembly_recipe_rate.step.components.what",
      whatDefault:
        "Find the labour, material and plant items the build-up needs in the cost database, for example concrete, formwork and reinforcement for a wall, and read each rate and unit before you pull it in.",
      whyKey: "cases.build_an_assembly_recipe_rate.step.components.why",
      whyDefault:
        "An assembly is only as sound as the items under it, so each component has to carry a real, traceable rate. Choosing them from the database rather than typing numbers keeps every part of the recipe justifiable.",
      moduleLabel: "Cost Explorer",
      moduleLabelKey: "nav.cost_explorer",
      to: "/cost-explorer",
    },
    {
      id: "factors",
      icon: "Boxes",
      inputs: [
        {
          labelKey: "cases.build_an_assembly_recipe_rate.step.factors.in.items",
          label: "Selected component items",
        },
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.factors.in.output",
          label: "Output unit",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.factors.out.factors",
          label: "Per-unit factors",
        },
        {
          labelKey: "cases.build_an_assembly_recipe_rate.step.factors.out.rate",
          label: "Composite unit rate",
        },
      ],
      titleKey: "cases.build_an_assembly_recipe_rate.step.factors.title",
      titleDefault: "Set the recipe factors",
      whatKey: "cases.build_an_assembly_recipe_rate.step.factors.what",
      whatDefault:
        "Assemble the components into one recipe and set the factor each contributes per unit of output, such as the cubic metres of concrete, square metres of shutter and kilograms of steel in one square metre of wall. Let the composite rate roll up.",
      whyKey: "cases.build_an_assembly_recipe_rate.step.factors.why",
      whyDefault:
        "The factors are the engineering knowledge in the rate, and once they are right the assembly prices the work consistently every time. Getting the proportions correct once beats re-deriving them line by line and getting a different answer each go.",
      moduleLabel: "Assemblies",
      moduleLabelKey: "nav.assemblies",
      to: "/assemblies",
    },
    {
      id: "apply",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.apply.in.assembly",
          label: "Saved assembly",
        },
        {
          labelKey:
            "cases.build_an_assembly_recipe_rate.step.apply.in.quantity",
          label: "Output quantity",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_an_assembly_recipe_rate.step.apply.out.line",
          label: "Priced bill line",
        },
        {
          labelKey: "cases.build_an_assembly_recipe_rate.step.apply.out.rollup",
          label: "Rolled-up components",
        },
      ],
      titleKey: "cases.build_an_assembly_recipe_rate.step.apply.title",
      titleDefault: "Drive bill lines from it",
      whatKey: "cases.build_an_assembly_recipe_rate.step.apply.what",
      whatDefault:
        "Place the assembly into the bill and enter one output quantity, and watch it carry the concrete, shutter and steel through in the right proportions with a single composite rate on the line.",
      whyKey: "cases.build_an_assembly_recipe_rate.step.apply.why",
      whyDefault:
        "A saved assembly makes repeated pricing fast and, more importantly, consistent across a large bill. Change a component rate once and every line built on it moves together, so a price rise cannot be applied in one place and forgotten in ten.",
      moduleLabel: "BOQ",
      moduleLabelKey: "nav.boq",
      to: "/boq",
    },
  ],
};

export default playbook;
