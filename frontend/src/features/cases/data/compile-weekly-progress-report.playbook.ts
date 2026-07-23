// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Compile the weekly progress report".
//
// Update where the programme really is, pull the week's diary and photos as
// the evidence, and issue one clean report the client can trust. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "compile-weekly-progress-report",
  order: 170,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "developer-client"],
  icon: "FileBarChart",
  titleKey: "cases.compile_weekly_progress_report.title",
  titleDefault: "Compile the weekly progress report",
  descKey: "cases.compile_weekly_progress_report.desc",
  descDefault:
    "Mark up where the programme actually is, gather the week of diary entries and photos that prove it, and issue one honest report the client can read in two minutes.",
  estMinutes: 10,
  steps: [
    {
      id: "actuals",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.actuals.in.programme",
          label: "Master programme",
        },
        {
          labelKey: "cases.compile_weekly_progress_report.step.actuals.in.week",
          label: "Progress this week",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.actuals.out.percent",
          label: "Updated percent complete",
        },
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.actuals.out.slippage",
          label: "Slippage vs baseline",
        },
      ],
      titleKey: "cases.compile_weekly_progress_report.step.actuals.title",
      titleDefault: "Update progress on the programme",
      whatKey: "cases.compile_weekly_progress_report.step.actuals.what",
      whatDefault:
        "Walk the programme and set the real percent complete on each active task, mark what started and finished this week, and let it show the slippage against the baseline rather than hiding it.",
      whyKey: "cases.compile_weekly_progress_report.step.actuals.why",
      whyDefault:
        "A report built on wishful percentages fools nobody for long and destroys your credibility when the truth lands. Honest actuals now are what make the finish date you quote believable.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "diary",
      icon: "NotebookPen",
      inputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.diary.in.entries",
          label: "Daily diary entries",
        },
        {
          labelKey: "cases.compile_weekly_progress_report.step.diary.in.photos",
          label: "Site photos",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.diary.out.evidence",
          label: "Dated evidence pack",
        },
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.diary.out.counts",
          label: "Labour and plant counts",
        },
      ],
      titleKey: "cases.compile_weekly_progress_report.step.diary.title",
      titleDefault: "Pull the week of evidence",
      whatKey: "cases.compile_weekly_progress_report.step.diary.what",
      whatDefault:
        "Gather the daily diary entries, labour and plant counts, weather and the site photos from the week, so the progress you are claiming is backed by a dated record of what actually happened on the ground.",
      whyKey: "cases.compile_weekly_progress_report.step.diary.why",
      whyDefault:
        "A number without evidence is just an opinion the client can dispute. The diary and photos are also the contemporaneous record that carries the weight if a delay claim is argued months later.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "publish",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.publish.in.progress",
          label: "Updated progress",
        },
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.publish.in.evidence",
          label: "Evidence pack",
        },
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.publish.in.lookahead",
          label: "Look-ahead",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.publish.out.report",
          label: "Weekly progress report",
        },
        {
          labelKey:
            "cases.compile_weekly_progress_report.step.publish.out.asks",
          label: "Client actions and risks",
        },
      ],
      titleKey: "cases.compile_weekly_progress_report.step.publish.title",
      titleDefault: "Publish the report",
      whatKey: "cases.compile_weekly_progress_report.step.publish.what",
      whatDefault:
        "Pull the progress, the key photos and the look-ahead into one report, call out the risks and the help you need from the client, and issue it on the same day every week.",
      whyKey: "cases.compile_weekly_progress_report.step.publish.why",
      whyDefault:
        "A report that always lands on the same day, reads straight and flags problems early is what builds the trust that gets decisions made fast. A late, spun report does the opposite.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
