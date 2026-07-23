// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up a new project".
//
// Stand a new job up so every later module has a clean spine to write to:
// create the record with the right region and currency, seed the bill, then lay
// the first programme. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "set-up-a-new-project",
  order: 130,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "developer-client"],
  icon: "Building2",
  titleKey: "cases.set_up_a_new_project.title",
  titleDefault: "Set up a new project",
  descKey: "cases.set_up_a_new_project.desc",
  descDefault:
    "Stand up a new job so everything downstream has one clean spine to attach to: create the record with the right region and currency, seed the bill of quantities and lay the first programme.",
  estMinutes: 8,
  steps: [
    {
      id: "create",
      icon: "Building2",
      inputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.create.in.brief",
          label: "Project brief",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.create.in.client",
          label: "Client details",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.create.in.region",
          label: "Region & currency",
        },
      ],
      outputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.create.out.record",
          label: "Project record",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.create.out.settings",
          label: "Region & currency set",
        },
      ],
      titleKey: "cases.set_up_a_new_project.step.create.title",
      titleDefault: "Create the project record",
      whatKey: "cases.set_up_a_new_project.step.create.what",
      whatDefault:
        "Open the new project form and enter the name, the client, the site location and the currency and region you will work and bill in. Save it to create the record every other module hangs off.",
      whyKey: "cases.set_up_a_new_project.step.create.why",
      whyDefault:
        "The region and currency set here decide which cost base, tax rules and units the whole job runs on. Getting them right on day one saves converting a half-built estimate later, which is where numbers get dropped.",
      moduleLabel: "Projects",
      moduleLabelKey: "nav.projects",
      to: "/projects/new",
    },
    {
      id: "boq",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.boq.in.record",
          label: "Project record",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.boq.in.scope",
          label: "Scope of works",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.boq.in.breakdown",
          label: "Trade breakdown",
        },
      ],
      outputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.boq.out.structure",
          label: "BOQ section structure",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.boq.out.positions",
          label: "First BOQ positions",
        },
      ],
      titleKey: "cases.set_up_a_new_project.step.boq.title",
      titleDefault: "Seed the bill of quantities",
      whatKey: "cases.set_up_a_new_project.step.boq.what",
      whatDefault:
        "Open the bill and lay out the section structure, by trade or by element, the way you intend to report and tender. Add the first known positions so the scope has a skeleton to grow on.",
      whyKey: "cases.set_up_a_new_project.step.boq.why",
      whyDefault:
        "A bill with a clear structure from the start is one every later estimator and the client can read at a glance. Deciding the breakdown now saves a painful reorganise once hundreds of lines are already in it.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "schedule",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.schedule.in.boq",
          label: "BOQ structure",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.schedule.in.sequence",
          label: "Trade sequence",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.schedule.in.dates",
          label: "Start & target dates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.set_up_a_new_project.step.schedule.out.programme",
          label: "Outline programme",
        },
        {
          labelKey: "cases.set_up_a_new_project.step.schedule.out.fronts",
          label: "Dated work fronts",
        },
      ],
      titleKey: "cases.set_up_a_new_project.step.schedule.title",
      titleDefault: "Lay the first programme",
      whatKey: "cases.set_up_a_new_project.step.schedule.what",
      whatDefault:
        "Open the schedule and sketch the major phases with rough durations and the order the trades follow, from enabling works through to handover. Set the start and the target completion date.",
      whyKey: "cases.set_up_a_new_project.step.schedule.why",
      whyDefault:
        "Even a coarse programme turns a priced scope into dated work fronts and shows at once whether the end date is achievable. It gives the team a shared picture of the job long before the detail is filled in.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
  ],
};

export default playbook;
