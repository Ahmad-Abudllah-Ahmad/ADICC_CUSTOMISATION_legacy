// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up a project and hand it over".
//
// A lifecycle playbook that mirrors the journey-map arcs at a higher level. It
// walks a user from first project setup all the way to final handover, crossing
// the modules in the order a job actually moves: create the project, price the
// work, schedule it, track it on site, then close it out. Every content string
// is a key plus an inline English default; these stay HERE and are never added
// to en.ts (only the framework chrome lives there). Module chips reuse existing
// translated nav/title keys so they localize for free.
//
// Routes used are all real (verified against app/App.tsx). Where no project-
// scoped variant exists (schedule, closeout) the plain route is used and the
// runner scopes it through the active-project context, exactly as the journey
// map does.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "project-end-to-end",
  order: 5,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "developer-client"],
  icon: "Layers",
  titleKey: "cases.project_end_to_end.title",
  titleDefault: "Set up a project and hand it over",
  descKey: "cases.project_end_to_end.desc",
  descDefault:
    "Take a job from the very first setup right through to handover. Create it, price the work, plan the programme, track it on site, then close it out clean. Five steps across the full lifecycle.",
  estMinutes: 20,
  steps: [
    {
      id: "create",
      icon: "Building2",
      inputs: [
        {
          labelKey: "cases.project_end_to_end.step.create.in.brief",
          label: "Project brief",
        },
        {
          labelKey: "cases.project_end_to_end.step.create.in.client",
          label: "Client details",
        },
      ],
      outputs: [
        {
          labelKey: "cases.project_end_to_end.step.create.out.project",
          label: "Project record",
        },
        {
          labelKey: "cases.project_end_to_end.step.create.out.currency",
          label: "Billing currency",
        },
      ],
      titleKey: "cases.project_end_to_end.step.create.title",
      titleDefault: "Create the project",
      whatKey: "cases.project_end_to_end.step.create.what",
      whatDefault:
        "Open the new project form and enter the essentials: name, client, site location and the currency you will bill in. Save it to spin up the project record everything else attaches to.",
      whyKey: "cases.project_end_to_end.step.create.why",
      whyDefault:
        "The project record is the spine that holds the estimate, the programme and the site log together. Get it right first and every later module has one place to write to.",
      moduleLabel: "Projects",
      moduleLabelKey: "nav.projects",
      to: "/projects/new",
    },
    {
      id: "estimate",
      icon: "Calculator",
      inputs: [
        {
          labelKey: "cases.project_end_to_end.step.estimate.in.project",
          label: "Project record",
        },
        {
          labelKey: "cases.project_end_to_end.step.estimate.in.rates",
          label: "Cost database rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.project_end_to_end.step.estimate.out.boq",
          label: "Priced BOQ",
        },
        {
          labelKey: "cases.project_end_to_end.step.estimate.out.budget",
          label: "Project budget",
        },
      ],
      titleKey: "cases.project_end_to_end.step.estimate.title",
      titleDefault: "Build the estimate",
      whatKey: "cases.project_end_to_end.step.estimate.what",
      whatDefault:
        "Open the bill of quantities and build up positions with their quantities and unit rates, pulling from the cost database or your saved assemblies. The running total climbs as you go.",
      whyKey: "cases.project_end_to_end.step.estimate.why",
      whyDefault:
        "The priced bill is the agreed scope in numbers. It sets the budget line the programme is resourced against and that site progress gets measured back to.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "schedule",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.project_end_to_end.step.schedule.in.scope",
          label: "Priced scope",
        },
        {
          labelKey: "cases.project_end_to_end.step.schedule.in.activities",
          label: "Activity list",
        },
      ],
      outputs: [
        {
          labelKey: "cases.project_end_to_end.step.schedule.out.programme",
          label: "Project programme",
        },
        {
          labelKey: "cases.project_end_to_end.step.schedule.out.critical",
          label: "Critical path",
        },
      ],
      titleKey: "cases.project_end_to_end.step.schedule.title",
      titleDefault: "Plan the schedule",
      whatKey: "cases.project_end_to_end.step.schedule.what",
      whatDefault:
        "Open the schedule and lay out the activities, give each a duration and link them in the sequence the trades actually follow. The critical path lights up the tasks that set the completion date.",
      whyKey: "cases.project_end_to_end.step.schedule.why",
      whyDefault:
        "A schedule converts a priced scope into dated work fronts. It tells the site team what comes next and surfaces a slip while there is still float to absorb it.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "track",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey: "cases.project_end_to_end.step.track.in.programme",
          label: "Project programme",
        },
        {
          labelKey: "cases.project_end_to_end.step.track.in.site",
          label: "Daily site activity",
        },
      ],
      outputs: [
        {
          labelKey: "cases.project_end_to_end.step.track.out.diary",
          label: "Daily diary entries",
        },
        {
          labelKey: "cases.project_end_to_end.step.track.out.progress",
          label: "Progress record",
        },
      ],
      titleKey: "cases.project_end_to_end.step.track.title",
      titleDefault: "Track work on site",
      whatKey: "cases.project_end_to_end.step.track.what",
      whatDefault:
        "Keep the daily diary as the job runs, logging progress, the crews on site, plant, deliveries and the weather each day. Every entry stacks into a dated history of the works.",
      whyKey: "cases.project_end_to_end.step.track.why",
      whyDefault:
        "A daily record shows actual progress against both the programme and the budget. It is also the first file you open when a delay, a variation or a claim needs proving.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "handover",
      icon: "Handshake",
      inputs: [
        {
          labelKey: "cases.project_end_to_end.step.handover.in.works",
          label: "Finished works",
        },
        {
          labelKey: "cases.project_end_to_end.step.handover.in.docs",
          label: "O&M manuals & warranties",
        },
      ],
      outputs: [
        {
          labelKey: "cases.project_end_to_end.step.handover.out.signoff",
          label: "Client sign-off",
        },
        {
          labelKey: "cases.project_end_to_end.step.handover.out.closed",
          label: "Closed-out project",
        },
      ],
      titleKey: "cases.project_end_to_end.step.handover.title",
      titleDefault: "Hand over the project",
      whatKey: "cases.project_end_to_end.step.handover.what",
      whatDefault:
        "Open handover and closeout to clear the punch list, gather the O and M manuals and warranties, and get the client sign-off.",
      whyKey: "cases.project_end_to_end.step.handover.why",
      whyDefault:
        "A tidy handover closes the job cleanly. The client walks away with a finished, documented building and you keep a full record of how it was delivered, snags and all.",
      moduleLabel: "Handover",
      moduleLabelKey: "closeout.title",
      to: "/closeout",
    },
  ],
};

export default playbook;
