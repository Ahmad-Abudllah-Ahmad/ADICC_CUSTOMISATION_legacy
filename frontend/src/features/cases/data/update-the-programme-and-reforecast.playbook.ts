// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Update the programme and reforecast".
//
// Take the actual progress the site reports, mark activities complete or part
// complete, let the schedule reforecast the finish date, spot where the job has
// slipped against the baseline, and report the new forecast with the reasons
// behind it. Content strings are key plus inline English default and live only
// here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "update-the-programme-and-reforecast",
  order: 264,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager"],
  icon: "CalendarClock",
  titleKey: "cases.update_the_programme_and_reforecast.title",
  titleDefault: "Update the programme and reforecast",
  descKey: "cases.update_the_programme_and_reforecast.desc",
  descDefault:
    "Take the actual progress the site reports, mark activities complete or part complete, let the schedule reforecast the finish date, spot where the job has slipped against the baseline, and report the new forecast with the reasons behind it.",
  estMinutes: 11,
  steps: [
    {
      id: "collect",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.collect.in.fieldtime",
          label: "Booked field hours",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.collect.in.diary",
          label: "Daily diary",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.collect.out.actuals",
          label: "Actual progress data",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.collect.out.completed",
          label: "Completed quantities",
        },
      ],
      titleKey: "cases.update_the_programme_and_reforecast.step.collect.title",
      titleDefault: "Collect actual progress from the field",
      whatKey: "cases.update_the_programme_and_reforecast.step.collect.what",
      whatDefault:
        "Pull the real progress off the site: hours booked, the daily diary, what each gang actually finished this week. Get it from the people doing the work, not from a guess made in the office.",
      whyKey: "cases.update_the_programme_and_reforecast.step.collect.why",
      whyDefault:
        "A reforecast is only as honest as the numbers going into it. Taking progress straight from field time and the diary is what stops the update becoming wishful thinking.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "mark",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.mark.in.actuals",
          label: "Actual progress data",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.mark.in.activities",
          label: "Live activities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.mark.out.status",
          label: "Updated activity status",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.mark.out.remaining",
          label: "Revised remaining durations",
        },
      ],
      titleKey: "cases.update_the_programme_and_reforecast.step.mark.title",
      titleDefault: "Mark activities complete or part complete",
      whatKey: "cases.update_the_programme_and_reforecast.step.mark.what",
      whatDefault:
        "Go through the activities that were live and set each one honestly: done, part done with a real percentage, or not started. Update remaining durations where a task is running slower or faster than planned.",
      whyKey: "cases.update_the_programme_and_reforecast.step.mark.why",
      whyDefault:
        "Rounding a job up to done when it is at eighty percent is how programmes drift and everyone stops trusting them. Marking progress honestly is what keeps the schedule worth reading.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "reforecast",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.reforecast.in.status",
          label: "Updated progress",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.reforecast.in.logic",
          label: "Programme logic",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.reforecast.out.forecast",
          label: "Forecast finish date",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.reforecast.out.criticalpath",
          label: "Shifted critical path",
        },
      ],
      titleKey:
        "cases.update_the_programme_and_reforecast.step.reforecast.title",
      titleDefault: "Reforecast the finish date",
      whatKey: "cases.update_the_programme_and_reforecast.step.reforecast.what",
      whatDefault:
        "Let the schedule roll the actuals through the logic and recalculate. Read the new forecast finish, watch how the critical path has shifted, and see which activities have now pulled the completion date with them.",
      whyKey: "cases.update_the_programme_and_reforecast.step.reforecast.why",
      whyDefault:
        "The value of a live programme is that it tells you where you will land, not just where you have been. Reforecasting off real progress is what turns last week numbers into a decision you can act on.",
      moduleLabel: "Advanced schedule",
      moduleLabelKey: "nav.schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "slippage",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.slippage.in.forecast",
          label: "New forecast",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.slippage.in.baseline",
          label: "Baseline programme",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.slippage.out.slippage",
          label: "Baseline slippage",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.slippage.out.causes",
          label: "Delay causes",
        },
      ],
      titleKey: "cases.update_the_programme_and_reforecast.step.slippage.title",
      titleDefault: "Spot slippage against the baseline",
      whatKey: "cases.update_the_programme_and_reforecast.step.slippage.what",
      whatDefault:
        "Compare the reforecast to the baseline you locked and pick out where the job has slipped: which milestones have moved, how much float has been eaten, and which delays trace back to a change rather than to production.",
      whyKey: "cases.update_the_programme_and_reforecast.step.slippage.why",
      whyDefault:
        "Knowing you are late is not enough, you have to know why and whose account it sits on. Tying slippage back to changes is what protects an extension of time claim before the delay is forgotten.",
      moduleLabel: "Change intelligence",
      moduleLabelKey: "nav.change_intelligence",
      to: "/change-intelligence",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.report.in.forecast",
          label: "Reforecast finish",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.report.in.causes",
          label: "Slippage & causes",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.report.out.report",
          label: "Forecast report",
        },
        {
          labelKey:
            "cases.update_the_programme_and_reforecast.step.report.out.recovery",
          label: "Recovery actions",
        },
      ],
      titleKey: "cases.update_the_programme_and_reforecast.step.report.title",
      titleDefault: "Report the new forecast",
      whatKey: "cases.update_the_programme_and_reforecast.step.report.what",
      whatDefault:
        "Issue the updated forecast to the client and the team with the reasons written plainly: what moved, by how much, why, and what is being done to pull it back. Keep it short enough that people actually read it.",
      whyKey: "cases.update_the_programme_and_reforecast.step.report.why",
      whyDefault:
        "A forecast that stays on the planner screen changes nothing. Reporting it clearly, with the reasons, is what lets the client trust the number and lets the team agree the recovery before the next cycle.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
