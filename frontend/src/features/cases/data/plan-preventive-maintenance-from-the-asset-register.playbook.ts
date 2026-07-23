// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Plan preventive maintenance from the asset register".
//
// Turn the assets you hold into a schedule of planned care: pick what needs it,
// set the recurring service tasks, and check the coverage before the first year.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "plan-preventive-maintenance-from-the-asset-register",
  order: 272,
  category: "handover",
  companyTypes: ["owner-operator", "developer-client"],
  stage: "operate",
  icon: "CalendarClock",
  titleKey: "cases.plan_preventive_maintenance_from_the_asset_register.title",
  titleDefault: "Plan preventive maintenance from the asset register",
  descKey: "cases.plan_preventive_maintenance_from_the_asset_register.desc",
  descDefault:
    "Turn the asset register into a preventive maintenance plan: pick the assets that need scheduled care, set their service tasks and frequencies, and check the coverage before the first year runs.",
  longDescKey:
    "cases.plan_preventive_maintenance_from_the_asset_register.longdesc",
  longDescDefault:
    "Reactive-only maintenance is how an operator ends up firefighting failures that a cheap scheduled visit would have prevented. This case reads the assets you already hold, turns the ones that matter into recurring service tasks at the right frequency, and reports the coverage so nothing critical is left off the plan.",
  estMinutes: 9,
  steps: [
    {
      id: "register",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.register.in.register",
          label: "Asset register",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.register.in.criticality",
          label: "Asset criticality",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.register.out.list",
          label: "Maintainable asset list",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.register.out.intervals",
          label: "Service intervals",
        },
      ],
      titleKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.register.title",
      titleDefault: "Pick the assets that need planned care",
      whatKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.register.what",
      whatDefault:
        "Open the asset register and mark the equipment that needs scheduled attention, from the plant that must not fail to the items a warranty says to service. Note the maker's interval for each.",
      whyKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.register.why",
      whyDefault:
        "The register is the only complete list of what you actually own to maintain. Starting the plan from it, rather than memory, is what stops a critical unit being missed until it breaks.",
      moduleLabel: "Assets",
      moduleLabelKey: "nav.assets",
      to: "/assets",
    },
    {
      id: "schedule",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.in.list",
          label: "Maintainable asset list",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.in.intervals",
          label: "Service intervals",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.out.plan",
          label: "Planned maintenance schedule",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.out.tasks",
          label: "Assigned tasks",
        },
      ],
      titleKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.title",
      titleDefault: "Set the recurring service tasks",
      whatKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.what",
      whatDefault:
        "Create the recurring service tasks against each asset at its interval, say who does them and what each visit checks, so the work is queued before it is due rather than after it fails.",
      whyKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.schedule.why",
      whyDefault:
        "A frequency in a manual does nothing until it is a task with an owner and a date. Turning the intervals into a live schedule is what actually gets the filter changed and the belt checked on time.",
      moduleLabel: "Service",
      moduleLabelKey: "nav.service",
      to: "/projects/:projectId/service",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.report.in.plan",
          label: "Planned maintenance schedule",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.report.in.register",
          label: "Asset register",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.report.out.coverage",
          label: "Coverage report",
        },
        {
          labelKey:
            "cases.plan_preventive_maintenance_from_the_asset_register.step.report.out.load",
          label: "Annual maintenance load",
        },
      ],
      titleKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.report.title",
      titleDefault: "Check the coverage and load",
      whatKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.report.what",
      whatDefault:
        "Run a report that lines the schedule up against the register to show which assets are covered, which are not, and how much planned work lands in each month. Close the gaps.",
      whyKey:
        "cases.plan_preventive_maintenance_from_the_asset_register.step.report.why",
      whyDefault:
        "A plan you cannot see the holes in is a plan with holes. The coverage view is what proves every critical asset is on the schedule and that the workload is spread, not stacked into one week.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
