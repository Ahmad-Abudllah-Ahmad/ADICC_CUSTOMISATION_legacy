// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build the baseline programme".
//
// Turn the agreed scope and the priced BOQ into a baseline programme: list the
// activities, set durations and logic links, add the milestones and calendars,
// sanity-check the critical path, then baseline it so every later report is
// measured against a fixed line. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-the-baseline-programme",
  order: 263,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager"],
  icon: "CalendarClock",
  titleKey: "cases.build_the_baseline_programme.title",
  titleDefault: "Build the baseline programme",
  descKey: "cases.build_the_baseline_programme.desc",
  descDefault:
    "Turn the agreed scope and the priced BOQ into a baseline programme: list the activities, set durations and logic links, add the milestones and calendars, check the critical path, then baseline it so progress has a fixed line to be measured against.",
  estMinutes: 12,
  steps: [
    {
      id: "activities",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.build_the_baseline_programme.step.activities.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.activities.in.scope",
          label: "Agreed scope",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.activities.out.activities",
          label: "Activity list",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.activities.out.wbs",
          label: "Work breakdown",
        },
      ],
      titleKey: "cases.build_the_baseline_programme.step.activities.title",
      titleDefault: "List the activities from the scope",
      whatKey: "cases.build_the_baseline_programme.step.activities.what",
      whatDefault:
        "Walk the priced BOQ and the scope and turn the work into a list of activities at the level you will actually manage: a floor of blockwork, a run of drainage, first fix to a wing, not one line per BOQ item and not a single summary bar.",
      whyKey: "cases.build_the_baseline_programme.step.activities.why",
      whyDefault:
        "The programme only holds up if the activity list matches the work that has been priced. Building it straight off the BOQ is what keeps the schedule, the money and the site talking about the same thing.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "durations",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.durations.in.activities",
          label: "Activity list",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.durations.in.quantities",
          label: "Quantities & crews",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.durations.out.durations",
          label: "Activity durations",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.durations.out.links",
          label: "Logic links",
        },
      ],
      titleKey: "cases.build_the_baseline_programme.step.durations.title",
      titleDefault: "Set durations and logic links",
      whatKey: "cases.build_the_baseline_programme.step.durations.what",
      whatDefault:
        "Give each activity a realistic duration from the quantities and the crew you plan to run, then link the activities in the order they must happen so that moving one moves the ones that depend on it.",
      whyKey: "cases.build_the_baseline_programme.step.durations.why",
      whyDefault:
        "Durations without links give you a wish list, not a programme. It is the logic between activities that lets the schedule show what a delay really costs downstream.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "milestones",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.milestones.in.network",
          label: "Linked activities",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.milestones.in.dates",
          label: "Contract dates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.milestones.out.milestones",
          label: "Key milestones",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.milestones.out.calendars",
          label: "Working calendars",
        },
      ],
      titleKey: "cases.build_the_baseline_programme.step.milestones.title",
      titleDefault: "Add milestones and calendars",
      whatKey: "cases.build_the_baseline_programme.step.milestones.what",
      whatDefault:
        "Mark the fixed dates that matter, start on site, sectional handovers, practical completion, and set working calendars that respect holidays, shift patterns and the weather windows the trades cannot beat.",
      whyKey: "cases.build_the_baseline_programme.step.milestones.why",
      whyDefault:
        "Milestones are the dates the client and the contract care about, and calendars are what stop the programme promising work on days no one is on site. Without them the finish date is fiction.",
      moduleLabel: "Advanced schedule",
      moduleLabelKey: "nav.schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "critical-path",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.critical-path.in.network",
          label: "Scheduled network",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.critical-path.in.milestones",
          label: "Milestone dates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.critical-path.out.criticalpath",
          label: "Verified critical path",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.critical-path.out.fixes",
          label: "Corrected logic",
        },
      ],
      titleKey: "cases.build_the_baseline_programme.step.critical-path.title",
      titleDefault: "Check the critical path",
      whatKey: "cases.build_the_baseline_programme.step.critical-path.what",
      whatDefault:
        "Follow the chain of activities that drives the finish date and read it against common sense. Look for missing links, negative float, and activities that show no slack when everyone on site knows they have some.",
      whyKey: "cases.build_the_baseline_programme.step.critical-path.why",
      whyDefault:
        "A critical path that does not match how the job will really run will send you chasing the wrong activities the moment things slip. Sanity-checking it before you baseline is cheaper than finding out on site.",
      moduleLabel: "Advanced schedule",
      moduleLabelKey: "nav.schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "baseline",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.baseline.in.programme",
          label: "Checked programme",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.baseline.in.criticalpath",
          label: "Critical path",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_the_baseline_programme.step.baseline.out.baseline",
          label: "Baselined programme",
        },
        {
          labelKey:
            "cases.build_the_baseline_programme.step.baseline.out.snapshot",
          label: "Planned-date snapshot",
        },
      ],
      titleKey: "cases.build_the_baseline_programme.step.baseline.title",
      titleDefault: "Baseline and issue",
      whatKey: "cases.build_the_baseline_programme.step.baseline.what",
      whatDefault:
        "Lock the programme as the baseline, snapshot the planned dates, and issue it so that from now on every update is compared to this fixed line rather than to last week guess.",
      whyKey: "cases.build_the_baseline_programme.step.baseline.why",
      whyDefault:
        "Progress means nothing without a line to measure it against. Baselining is the moment the programme stops being a draft and becomes the yardstick the whole job is judged by.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
