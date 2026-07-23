// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a baseline and track progress".
//
// Plan the works, freeze a baseline, then feed real site progress back so the
// schedule shows where you are against where you said you would be. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "schedule-and-track",
  order: 35,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "subcontractor"],
  icon: "CalendarClock",
  titleKey: "cases.schedule_and_track.title",
  titleDefault: "Build a baseline and track progress",
  descKey: "cases.schedule_and_track.desc",
  descDefault:
    "Plan the programme, freeze a baseline to measure against, feed real progress back from site and read the variance so slippage surfaces early.",
  estMinutes: 12,
  steps: [
    {
      id: "plan",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey: "cases.schedule_and_track.step.plan.in.scope",
          label: "Scope of works",
        },
        {
          labelKey: "cases.schedule_and_track.step.plan.in.sequence",
          label: "Trade sequence",
        },
      ],
      outputs: [
        {
          labelKey: "cases.schedule_and_track.step.plan.out.programme",
          label: "Linked activity programme",
        },
        {
          labelKey: "cases.schedule_and_track.step.plan.out.critical",
          label: "Critical path",
        },
      ],
      titleKey: "cases.schedule_and_track.step.plan.title",
      titleDefault: "Lay out the programme",
      whatKey: "cases.schedule_and_track.step.plan.what",
      whatDefault:
        "Build out the activities, set a duration on each and link them in the order the trades follow so the critical path falls out. Group the work the way you will report it later, by trade, by zone or by phase.",
      whyKey: "cases.schedule_and_track.step.plan.why",
      whyDefault:
        "The programme is your promise on when the job finishes. A clear critical path separates the delays that genuinely push the finish date from the ones that only eat float.",
      moduleLabel: "Schedule",
      moduleLabelKey: "schedule.title",
      to: "/schedule",
    },
    {
      id: "baseline",
      icon: "Flag",
      inputs: [
        {
          labelKey: "cases.schedule_and_track.step.baseline.in.programme",
          label: "Agreed programme",
        },
        {
          labelKey: "cases.schedule_and_track.step.baseline.in.signoff",
          label: "Client sign-off",
        },
      ],
      outputs: [
        {
          labelKey: "cases.schedule_and_track.step.baseline.out.baseline",
          label: "Frozen baseline",
        },
        {
          labelKey: "cases.schedule_and_track.step.baseline.out.target",
          label: "Baseline finish date",
        },
      ],
      titleKey: "cases.schedule_and_track.step.baseline.title",
      titleDefault: "Freeze the baseline",
      whatKey: "cases.schedule_and_track.step.baseline.what",
      whatDefault:
        "Save the agreed programme as a baseline before a spade goes in the ground. From here on every update is read against this frozen copy.",
      whyKey: "cases.schedule_and_track.step.baseline.why",
      whyDefault:
        "With no baseline there is nothing to be late against. Freezing it is what converts a plan into a yardstick that holds up when an extension of time is argued.",
      moduleLabel: "Advanced scheduling",
      moduleLabelKey: "onboarding.mod_schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "actuals",
      icon: "HardHat",
      inputs: [
        {
          labelKey: "cases.schedule_and_track.step.actuals.in.activities",
          label: "Programme activities",
        },
        {
          labelKey: "cases.schedule_and_track.step.actuals.in.field",
          label: "Field timesheets",
        },
      ],
      outputs: [
        {
          labelKey: "cases.schedule_and_track.step.actuals.out.dates",
          label: "Actual start and finish",
        },
        {
          labelKey: "cases.schedule_and_track.step.actuals.out.hours",
          label: "Booked labour hours",
        },
      ],
      titleKey: "cases.schedule_and_track.step.actuals.title",
      titleDefault: "Capture real progress",
      whatKey: "cases.schedule_and_track.step.actuals.what",
      whatDefault:
        "Record actual start and finish dates and the hours booked from the field, so the schedule mirrors what the crews really did this period.",
      whyKey: "cases.schedule_and_track.step.actuals.why",
      whyDefault:
        "A programme nobody updates is fiction by the second week. Feeding site data back is the only thing that keeps the forecast honest and the completion date believable.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "variance",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.schedule_and_track.step.variance.in.updated",
          label: "Updated programme",
        },
        {
          labelKey: "cases.schedule_and_track.step.variance.in.baseline",
          label: "Frozen baseline",
        },
      ],
      outputs: [
        {
          labelKey: "cases.schedule_and_track.step.variance.out.slippage",
          label: "Slippage variance",
        },
        {
          labelKey: "cases.schedule_and_track.step.variance.out.float",
          label: "Remaining float",
        },
      ],
      titleKey: "cases.schedule_and_track.step.variance.title",
      titleDefault: "Read the variance",
      whatKey: "cases.schedule_and_track.step.variance.what",
      whatDefault:
        "Set the updated programme against the baseline and read the slippage and the remaining float. The advanced view shows the critical path shifting as each progress update lands.",
      whyKey: "cases.schedule_and_track.step.variance.why",
      whyDefault:
        "A variance spotted early is still a decision you can make. The whole point of tracking is to act on a two-week slip now, not to document a two-month one at the end.",
      moduleLabel: "Advanced scheduling",
      moduleLabelKey: "onboarding.mod_schedule_advanced",
      to: "/schedule-advanced",
    },
  ],
};

export default playbook;
