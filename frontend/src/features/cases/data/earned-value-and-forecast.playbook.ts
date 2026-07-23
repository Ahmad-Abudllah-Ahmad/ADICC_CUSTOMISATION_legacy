// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Earned value and forecast".
//
// Measure where the project really is against plan and budget: update the
// programme, read the EVM indices and forecast the outturn cost and date.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "earned-value-and-forecast",
  order: 90,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "cost-consultant"],
  icon: "TrendingUp",
  titleKey: "cases.earned_value_and_forecast.title",
  titleDefault: "Earned value and forecast",
  descKey: "cases.earned_value_and_forecast.desc",
  descDefault:
    "See where the job truly stands against the plan and the budget: bring the programme current, read the CPI and SPI, and put a credible number on the outturn cost and finish date.",
  estMinutes: 13,
  steps: [
    {
      id: "update",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.update.in.baseline",
          label: "Baseline programme",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.update.in.progress",
          label: "Period progress",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.update.in.costs",
          label: "Committed & actual costs",
        },
      ],
      outputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.update.out.current",
          label: "Programme at data date",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.update.out.percent",
          label: "Percent complete set",
        },
      ],
      titleKey: "cases.earned_value_and_forecast.step.update.title",
      titleDefault: "Update the programme",
      whatKey: "cases.earned_value_and_forecast.step.update.what",
      whatDefault:
        "Roll every activity forward to the data date, set an honest percent complete on the ones in progress, and make sure the committed and actual costs for the period are booked in.",
      whyKey: "cases.earned_value_and_forecast.step.update.why",
      whyDefault:
        "Earned value inherits every optimistic progress claim you feed it. A disciplined cut-off, with no work counted before it is truly done, is the only thing that makes the indices worth reading.",
      moduleLabel: "Schedule",
      moduleLabelKey: "schedule.title",
      to: "/schedule",
    },
    {
      id: "measure",
      icon: "LineChart",
      inputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.measure.in.programme",
          label: "Updated programme",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.measure.in.planned",
          label: "Planned value",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.measure.in.actual",
          label: "Actual cost",
        },
      ],
      outputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.measure.out.indices",
          label: "CPI and SPI",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.measure.out.variance",
          label: "Cost & schedule variance",
        },
      ],
      titleKey: "cases.earned_value_and_forecast.step.measure.title",
      titleDefault: "Read the earned value",
      whatKey: "cases.earned_value_and_forecast.step.measure.what",
      whatDefault:
        "Compare the value you have earned against what was planned and what you have spent, then read the cost and schedule performance indices and the variances they produce.",
      whyKey: "cases.earned_value_and_forecast.step.measure.why",
      whyDefault:
        "A superintendent who says the job feels behind is guessing; an SPI of 0.9 is a measurement. Anything under one on cost or schedule means the gap is trending wider, not sitting still.",
      moduleLabel: "Value",
      moduleLabelKey: "nav.value",
      to: "/projects/:projectId/value",
    },
    {
      id: "forecast",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.in.indices",
          label: "Performance indices",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.in.budget",
          label: "Budget at completion",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.in.baseline",
          label: "Baseline finish date",
        },
      ],
      outputs: [
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.out.eac",
          label: "Estimate at completion",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.out.finish",
          label: "Forecast finish date",
        },
        {
          labelKey: "cases.earned_value_and_forecast.step.forecast.out.report",
          label: "Outturn report",
        },
      ],
      titleKey: "cases.earned_value_and_forecast.step.forecast.title",
      titleDefault: "Forecast the outturn",
      whatKey: "cases.earned_value_and_forecast.step.forecast.what",
      whatDefault:
        "Extend the current cost and productivity trend to an estimate at completion and a likely finish date, then set both against the budget and the baseline for the report.",
      whyKey: "cases.earned_value_and_forecast.step.forecast.why",
      whyDefault:
        "A forecast overrun flagged in month four is a problem you can still steer; the same number in month ten is just an apology. Early warning is the whole reason to run earned value at all.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
