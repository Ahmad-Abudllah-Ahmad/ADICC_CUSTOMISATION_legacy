// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Prepare a method statement and risk assessment".
//
// Build a RAMS for a work package before it starts: describe the safe method,
// identify hazards and controls, assign responsibilities, get it reviewed and
// issued, and make it available on site. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "prepare-a-method-statement-and-risk-assessment",
  order: 262,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor"],
  roles: ["hse-officer", "site-manager"],
  icon: "ClipboardList",
  titleKey: "cases.prepare_a_method_statement_and_risk_assessment.title",
  titleDefault: "Prepare a method statement and risk assessment",
  descKey: "cases.prepare_a_method_statement_and_risk_assessment.desc",
  descDefault:
    "Build a method statement and risk assessment for a work package before it starts, describe the safe method, identify hazards and controls, assign responsibilities, get it reviewed and issued, and make it available on site.",
  estMinutes: 12,
  steps: [
    {
      id: "method",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.method.in.package",
          label: "Work package scope",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.method.in.drawings",
          label: "Drawings & layout",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.method.out.method",
          label: "Method statement",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.method.out.sequence",
          label: "Work sequence",
        },
      ],
      titleKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.method.title",
      titleDefault: "Describe the safe method",
      whatKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.method.what",
      whatDefault:
        "Set out how the work package will actually be done step by step, the sequence, the plant and equipment, access and the people involved, in plain language a crew can follow.",
      whyKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.method.why",
      whyDefault:
        "A method statement turns a vague plan into an agreed way of working that everyone signs up to. When the sequence is written down, the whole crew works to the same picture instead of improvising.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "hazards",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.in.method",
          label: "Method statement",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.in.steps",
          label: "Work steps",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.out.hazards",
          label: "Hazard list",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.out.controls",
          label: "Controls & risk ratings",
        },
      ],
      titleKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.title",
      titleDefault: "Identify hazards and controls",
      whatKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.what",
      whatDefault:
        "Go through each step and list the hazards it creates, then set the control for each one, rate the risk before and after the control so the level of danger is clear.",
      whyKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.hazards.why",
      whyDefault:
        "The risk assessment is where you prove the method is safe, not just workable. Rating the risk before and after controls shows exactly why each control is there and what happens without it.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "responsibilities",
      icon: "Users",
      inputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.in.controls",
          label: "Control measures",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.in.team",
          label: "Site team & roles",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.out.owners",
          label: "Assigned duty holders",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.out.matrix",
          label: "Responsibility matrix",
        },
      ],
      titleKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.title",
      titleDefault: "Assign responsibilities",
      whatKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.what",
      whatDefault:
        "Name who is responsible for each control and each check, the supervisor, the appointed person for lifts, the first aider, so every duty in the plan has an owner.",
      whyKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.responsibilities.why",
      whyDefault:
        "A control with no name against it is a control nobody does. Assigning responsibility is what turns the paperwork into something that actually happens on site.",
      moduleLabel: "QMS",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "review",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.review.in.rams",
          label: "Draft RAMS",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.review.in.reviewer",
          label: "Responsible manager",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.review.out.approved",
          label: "Approved RAMS",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.review.out.revision",
          label: "Reference & revision",
        },
      ],
      titleKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.review.title",
      titleDefault: "Review and issue",
      whatKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.review.what",
      whatDefault:
        "Send the RAMS for review by the responsible manager, capture their comments, then issue the approved version with a clear reference and revision so there is one current copy.",
      whyKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.review.why",
      whyDefault:
        "Review catches the gaps before the work starts, not after an incident. A tracked issue and revision means the crew is never working to an old or unapproved method.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "available",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.available.in.approved",
          label: "Approved RAMS",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.available.in.crew",
          label: "Delivery crew",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.available.out.filed",
          label: "RAMS in project files",
        },
        {
          labelKey:
            "cases.prepare_a_method_statement_and_risk_assessment.step.available.out.briefed",
          label: "Briefed crew",
        },
      ],
      titleKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.available.title",
      titleDefault: "Make it available on site",
      whatKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.available.what",
      whatDefault:
        "Store the issued RAMS in the project files where the crew and any inspector can reach it, and brief the crew on it before the package starts.",
      whyKey:
        "cases.prepare_a_method_statement_and_risk_assessment.step.available.why",
      whyDefault:
        "A RAMS locked in an office does not protect anyone. Having the current version on site, briefed to the crew, is what makes it a working document and proves the work was planned safely.",
      moduleLabel: "Project files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
