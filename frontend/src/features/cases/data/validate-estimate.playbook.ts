// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Check an estimate before you send it".
//
// A short quality gate: run the validation rules over a priced BOQ, fix what
// they flag, then produce the client-ready report. Every content string is a
// key plus an inline English default and lives only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "validate-estimate",
  order: 15,
  category: "estimating",
  companyTypes: ["general-contractor", "cost-consultant", "subcontractor"],
  icon: "Calculator",
  titleKey: "cases.validate_estimate.title",
  titleDefault: "Check an estimate before you send it",
  descKey: "cases.validate_estimate.desc",
  descDefault:
    "Put a priced bill through the validation rules, clear every warning and error, then export a clean report you can hand straight to the client.",
  estMinutes: 8,
  steps: [
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.validate_estimate.step.boq.in.bill",
          label: "Priced bill of quantities",
        },
        {
          labelKey: "cases.validate_estimate.step.boq.in.rates",
          label: "Quantities and rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.validate_estimate.step.boq.out.reviewed",
          label: "Reviewed priced bill",
        },
        {
          labelKey: "cases.validate_estimate.step.boq.out.gaps",
          label: "Spotted blank cells",
        },
      ],
      titleKey: "cases.validate_estimate.step.boq.title",
      titleDefault: "Open the priced bill",
      whatKey: "cases.validate_estimate.step.boq.what",
      whatDefault:
        "Open the bill you are about to issue and confirm every position carries both a quantity and a rate. Blank cells and stray zeros are the first thing the validator hunts down, so a quick scan now saves surprises.",
      whyKey: "cases.validate_estimate.step.boq.why",
      whyDefault:
        "A gap you overlook is a gap the client finds first, usually in the meeting. Reviewing the bill yourself means the validation pass confirms good work rather than exposing a hole.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.validate_estimate.step.validate.in.bill",
          label: "Reviewed priced bill",
        },
        {
          labelKey: "cases.validate_estimate.step.validate.in.rules",
          label: "Validation rule sets",
        },
      ],
      outputs: [
        {
          labelKey: "cases.validate_estimate.step.validate.out.score",
          label: "Traffic-light score",
        },
        {
          labelKey: "cases.validate_estimate.step.validate.out.issues",
          label: "Linked errors and warnings",
        },
      ],
      titleKey: "cases.validate_estimate.step.validate.title",
      titleDefault: "Run the validation rules",
      whatKey: "cases.validate_estimate.step.validate.what",
      whatDefault:
        "Run the rule sets across the bill and read the traffic-light result. Each error and warning is linked to the exact position, so you can jump to the offending line and fix the cause rather than the symptom.",
      whyKey: "cases.validate_estimate.step.validate.why",
      whyDefault:
        "Missing quantities, zero prices, duplicate lines and rates outside a sane band are cheap to correct today and awkward to explain after issue. The score is your honest go or no-go signal.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.validate_estimate.step.report.in.bill",
          label: "Validated green bill",
        },
        {
          labelKey: "cases.validate_estimate.step.report.in.outcome",
          label: "Validation outcome",
        },
      ],
      outputs: [
        {
          labelKey: "cases.validate_estimate.step.report.out.summary",
          label: "Executive summary",
        },
        {
          labelKey: "cases.validate_estimate.step.report.out.breakdown",
          label: "Detailed cost breakdown",
        },
      ],
      titleKey: "cases.validate_estimate.step.report.title",
      titleDefault: "Export the report",
      whatKey: "cases.validate_estimate.step.report.what",
      whatDefault:
        "Once the bill reads green, export the executive summary alongside the detailed breakdown. The report ships the cost split and the validation outcome in one document.",
      whyKey: "cases.validate_estimate.step.report.why",
      whyDefault:
        "A report backed by a passed validation is one you can stand behind under questioning. It shows the client not just the total but that the total was checked against rules before it was sent.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reporting",
      to: "/reports",
    },
  ],
};

export default playbook;
