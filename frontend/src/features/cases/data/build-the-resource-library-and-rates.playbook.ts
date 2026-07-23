// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build the resource library and rates".
//
// Define labour, plant and materials once, build assemblies from them, and
// reuse the same resources to load the programme so estimate and plan agree.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-the-resource-library-and-rates",
  order: 318,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor", "subcontractor"],
  icon: "Calculator",
  titleKey: "cases.build_the_resource_library_and_rates.title",
  titleDefault: "Build the resource library and rates",
  descKey: "cases.build_the_resource_library_and_rates.desc",
  descDefault:
    "Define your labour, plant and materials once, build assemblies from them, and reuse the same resources to load the programme.",
  estMinutes: 8,
  steps: [
    {
      id: "define-resources",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.define-resources.in.labour",
          label: "Labour grades",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.define-resources.in.plant",
          label: "Plant items",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.define-resources.in.materials",
          label: "Material prices",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.define-resources.out.library",
          label: "Resource library",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.define-resources.out.rates",
          label: "Base rates",
        },
      ],
      titleKey:
        "cases.build_the_resource_library_and_rates.step.define-resources.title",
      titleDefault: "Define the resources",
      whatKey:
        "cases.build_the_resource_library_and_rates.step.define-resources.what",
      whatDefault:
        "In Resources, define labour grades, plant and materials, each with its base rate.",
      whyKey:
        "cases.build_the_resource_library_and_rates.step.define-resources.why",
      whyDefault:
        "One clean resource list is what every rate and every programme leans on. Change a base rate once and everything built from it updates.",
      moduleLabel: "Resources",
      to: "/resources",
    },
    {
      id: "build-assemblies",
      icon: "Combine",
      inputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.build-assemblies.in.resources",
          label: "Resource library",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.build-assemblies.in.rates",
          label: "Base rates",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.build-assemblies.in.factors",
          label: "Consumption factors",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.build-assemblies.out.recipes",
          label: "Assembly recipes",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.build-assemblies.out.unitrates",
          label: "Traceable unit rates",
        },
      ],
      titleKey:
        "cases.build_the_resource_library_and_rates.step.build-assemblies.title",
      titleDefault: "Build the assemblies",
      whatKey:
        "cases.build_the_resource_library_and_rates.step.build-assemblies.what",
      whatDefault:
        "In Assemblies, build recipes from those resources so each unit rate traces back to the labour, plant and material that make it up.",
      whyKey:
        "cases.build_the_resource_library_and_rates.step.build-assemblies.why",
      whyDefault:
        "A rate you cannot break down is a rate you cannot defend in a negotiation or a claim. Recipes show exactly what is inside the number.",
      moduleLabel: "Assemblies",
      to: "/assemblies",
    },
    {
      id: "load-programme",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.load-programme.in.resources",
          label: "Shared resources",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.load-programme.in.activities",
          label: "Programme activities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.load-programme.out.histogram",
          label: "Labour histogram",
        },
        {
          labelKey:
            "cases.build_the_resource_library_and_rates.step.load-programme.out.aligned",
          label: "Estimate-plan alignment",
        },
      ],
      titleKey:
        "cases.build_the_resource_library_and_rates.step.load-programme.title",
      titleDefault: "Load the programme",
      whatKey:
        "cases.build_the_resource_library_and_rates.step.load-programme.what",
      whatDefault:
        "In Schedule Advanced, load the programme with the same resources instead of inventing new ones.",
      whyKey:
        "cases.build_the_resource_library_and_rates.step.load-programme.why",
      whyDefault:
        "When the estimate and the programme share resources, the labour histogram and the cost match reality. Separate lists drift, and the plan stops agreeing with the price.",
      moduleLabel: "Schedule Advanced",
      to: "/schedule-advanced",
    },
  ],
};

export default playbook;
