// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Forecast project cash flow".
//
// Spread the priced work across the programme to see money in and money out
// month by month, then report the low points before they bite. Content strings
// are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "forecast-project-cash-flow",
  order: 145,
  category: "commercial",
  companyTypes: ["general-contractor", "developer-client", "cost-consultant"],
  icon: "LineChart",
  titleKey: "cases.forecast_project_cash_flow.title",
  titleDefault: "Forecast project cash flow",
  descKey: "cases.forecast_project_cash_flow.desc",
  descDefault:
    "Spread the priced work across the programme to see cash in and cash out month by month, find where the balance dips negative, and report it early enough to do something about it.",
  estMinutes: 12,
  steps: [
    {
      id: "phase",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.phase.in.bill",
          label: "Priced bill",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.phase.in.schedule",
          label: "Project schedule",
        },
      ],
      outputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.phase.out.curve",
          label: "Monthly cost curve",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.phase.out.activity",
          label: "Cost-loaded activities",
        },
      ],
      titleKey: "cases.forecast_project_cash_flow.step.phase.title",
      titleDefault: "Spread the cost over the programme",
      whatKey: "cases.forecast_project_cash_flow.step.phase.what",
      whatDefault:
        "Tie the priced bill to the schedule so each activity carries its cost, then let the spend spread across the timeline to give a month-by-month cost curve rather than one lump total.",
      whyKey: "cases.forecast_project_cash_flow.step.phase.why",
      whyDefault:
        "A total tells you what the job costs but not when the money leaves, and construction lives or dies on timing. Spreading cost over the programme turns the budget into the profile a cash forecast can be built on.",
      moduleLabel: "Schedule",
      moduleLabelKey: "nav.schedule",
      to: "/schedule",
    },
    {
      id: "flow",
      icon: "Banknote",
      inputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.flow.in.curve",
          label: "Monthly cost curve",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.flow.in.terms",
          label: "Payment terms",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.flow.in.retention",
          label: "Retention rules",
        },
      ],
      outputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.flow.out.balance",
          label: "Running cash balance",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.flow.out.lowpoint",
          label: "Negative low point",
        },
      ],
      titleKey: "cases.forecast_project_cash_flow.step.flow.title",
      titleDefault: "Build the cash flow",
      whatKey: "cases.forecast_project_cash_flow.step.flow.what",
      whatDefault:
        "Set the income against the cost curve using the payment terms, retention and the lag between valuation and money in, then read the running balance to find where it goes negative.",
      whyKey: "cases.forecast_project_cash_flow.step.flow.why",
      whyDefault:
        "A profitable job can still run out of cash mid-build because payment always lags spend. Seeing the low point in advance is what lets you arrange funding or reprofile work before it becomes a crisis on site.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.report.in.balance",
          label: "Running cash balance",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.report.in.actuals",
          label: "Actual valuations",
        },
      ],
      outputs: [
        {
          labelKey: "cases.forecast_project_cash_flow.step.report.out.report",
          label: "Cash flow report",
        },
        {
          labelKey: "cases.forecast_project_cash_flow.step.report.out.funding",
          label: "Funding requirement",
        },
      ],
      titleKey: "cases.forecast_project_cash_flow.step.report.title",
      titleDefault: "Report and manage it",
      whatKey: "cases.forecast_project_cash_flow.step.report.what",
      whatDefault:
        "Produce the cash flow report with the funding requirement and the peak exposure marked, and update it each period as actual valuations and payments replace the forecast ones.",
      whyKey: "cases.forecast_project_cash_flow.step.report.why",
      whyDefault:
        "A cash forecast is only useful if it reaches the people who arrange the money and is kept current. Refreshed every period, it turns from a one-off guess into an early warning the whole business can act on.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
