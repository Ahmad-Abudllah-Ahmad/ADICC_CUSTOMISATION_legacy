// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Produce a short-interval lookahead".
//
// Pull the next few weeks off the master programme, clear the constraints in
// front of each task, and commit a weekly plan the crews can actually make.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "produce-a-short-interval-lookahead",
  order: 200,
  category: "planning",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "CalendarClock",
  titleKey: "cases.produce_a_short_interval_lookahead.title",
  titleDefault: "Produce a short-interval lookahead",
  descKey: "cases.produce_a_short_interval_lookahead.desc",
  descDefault:
    "Pull the next two to three weeks off the master programme, clear the constraints sitting in front of each task, and commit a weekly plan the crews can genuinely make.",
  estMinutes: 10,
  steps: [
    {
      id: "pull",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.pull.in.programme",
          label: "Master programme",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.pull.in.window",
          label: "Two to three week window",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.pull.out.tasks",
          label: "Task-level activities",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.pull.out.lookahead",
          label: "Draft lookahead",
        },
      ],
      titleKey: "cases.produce_a_short_interval_lookahead.step.pull.title",
      titleDefault: "Pull the next weeks",
      whatKey: "cases.produce_a_short_interval_lookahead.step.pull.what",
      whatDefault:
        "Take the two to three weeks of work coming up off the master programme and break the tasks down to the level a foreman actually plans at: a pour, a lift, a room, not a summary bar.",
      whyKey: "cases.produce_a_short_interval_lookahead.step.pull.why",
      whyDefault:
        "The master programme sets the direction but is too coarse to run a week from. Breaking the near-term work down to real activities is what makes the plan something a gang can be held to.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "constraints",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.constraints.in.tasks",
          label: "Lookahead tasks",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.constraints.in.blockers",
          label: "Task constraints",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.constraints.out.cleared",
          label: "Constraints cleared",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.constraints.out.ready",
          label: "Ready tasks",
        },
      ],
      titleKey:
        "cases.produce_a_short_interval_lookahead.step.constraints.title",
      titleDefault: "Clear the constraints",
      whatKey: "cases.produce_a_short_interval_lookahead.step.constraints.what",
      whatDefault:
        "For each task, list what has to be true before it can start: design released, materials on site, preceding trade finished, permit live, access clear. Assign each blocker to someone and chase it down before the week begins.",
      whyKey: "cases.produce_a_short_interval_lookahead.step.constraints.why",
      whyDefault:
        "A task put on the plan before its constraints are cleared is a promise that will break and stall the trades behind it. Screening the blockers out first is what makes a weekly commitment worth the paper.",
      moduleLabel: "Advanced scheduling",
      moduleLabelKey: "onboarding.mod_schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "commit",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.commit.in.ready",
          label: "Ready tasks",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.commit.in.crews",
          label: "Crew capacity",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.commit.out.plan",
          label: "Weekly work plan",
        },
        {
          labelKey:
            "cases.produce_a_short_interval_lookahead.step.commit.out.ppc",
          label: "Promises-kept score",
        },
      ],
      titleKey: "cases.produce_a_short_interval_lookahead.step.commit.title",
      titleDefault: "Commit the weekly plan",
      whatKey: "cases.produce_a_short_interval_lookahead.step.commit.what",
      whatDefault:
        "Issue the weekly work plan of tasks that are genuinely ready, get each foreman to commit to what their crew will complete, and at week end measure how many of those promises were actually met.",
      whyKey: "cases.produce_a_short_interval_lookahead.step.commit.why",
      whyDefault:
        "Only planning work that is truly ready is what makes crews trust the plan and hit it. Tracking the promises kept, week on week, is the honest early signal of whether the programme is really under control.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
