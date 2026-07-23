// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Turn field time into payroll and labour cost".
//
// Take the approved hours off site, run them through payroll at the right grade
// and rate, and post the labour cost to the job so the cost report shows what
// the work actually cost. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "turn-field-time-into-payroll-and-labour-cost",
  order: 320,
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "Banknote",
  titleKey: "cases.turn_field_time_into_payroll_and_labour_cost.title",
  titleDefault: "Turn field time into payroll and labour cost",
  descKey: "cases.turn_field_time_into_payroll_and_labour_cost.desc",
  descDefault:
    "Take the approved hours off site, run them through payroll at the right grade and rate, and post the labour cost to the job so the cost report shows what the work actually cost.",
  estMinutes: 8,
  steps: [
    {
      id: "collect",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.in.timesheets",
          label: "Field timesheets",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.in.approval",
          label: "Supervisor approval",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.out.hours",
          label: "Approved hours",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.out.codes",
          label: "Hours by cost code",
        },
      ],
      titleKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.title",
      titleDefault: "Collect the approved timesheets",
      whatKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.what",
      whatDefault:
        "Pull the week of timesheets from the field, checked and approved by the supervisor, with hours booked by worker and against the right cost code.",
      whyKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.collect.why",
      whyDefault:
        "A payroll run off unapproved hours pays for time nobody signed for. Approved timesheets are the one clean source both the wage and the job cost are built on.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "run",
      icon: "Calculator",
      inputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.run.in.hours",
          label: "Approved hours",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.run.in.rates",
          label: "Grade & rate table",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.run.out.gross",
          label: "Gross pay",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.run.out.run",
          label: "Payroll run",
        },
      ],
      titleKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.run.title",
      titleDefault: "Run hours into gross pay",
      whatKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.run.what",
      whatDefault:
        "Turn the approved hours into gross pay for each worker, applying the grade, the rate and any overtime or allowances the agreement carries.",
      whyKey: "cases.turn_field_time_into_payroll_and_labour_cost.step.run.why",
      whyDefault:
        "The same hour costs a labourer rate and a foreman rate very differently. Pricing by grade is what makes the wage right and the labour cost real, not an average guess.",
      moduleLabel: "Payroll",
      moduleLabelKey: "nav.payroll",
      to: "/projects/:projectId/payroll",
    },
    {
      id: "post",
      icon: "ReceiptText",
      inputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.post.in.total",
          label: "Payroll total",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.post.in.codes",
          label: "Cost codes",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.post.out.posted",
          label: "Labour cost posted",
        },
        {
          labelKey:
            "cases.turn_field_time_into_payroll_and_labour_cost.step.post.out.costtodate",
          label: "Updated cost to date",
        },
      ],
      titleKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.post.title",
      titleDefault: "Post labour cost to the job",
      whatKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.post.what",
      whatDefault:
        "Post the payroll total to the project ledger against the right cost codes, so the labour spend sits alongside materials, plant and subcontract.",
      whyKey:
        "cases.turn_field_time_into_payroll_and_labour_cost.step.post.why",
      whyDefault:
        "A cost report missing its labour is telling you the job is cheaper than it is. Posting the wage bill to the job is what makes the cost to date complete and the margin honest.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
