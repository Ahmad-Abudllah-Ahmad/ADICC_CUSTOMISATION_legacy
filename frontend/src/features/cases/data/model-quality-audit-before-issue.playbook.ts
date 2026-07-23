// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Audit a model before it goes out".
//
// A BIM consultant case: run the checks that catch a bad model before a
// client or a site team opens it, coordinate base, live clashes and
// classification completeness. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "model-quality-audit-before-issue",
  order: 240,
  category: "bim",
  companyTypes: ["bim-consultant", "designer", "general-contractor"],
  icon: "Crosshair",
  titleKey: "cases.model_quality_audit_before_issue.title",
  titleDefault: "Audit a model before it goes out",
  descKey: "cases.model_quality_audit_before_issue.desc",
  descDefault:
    "Run the checks that catch a bad model before a client or a site team opens it: coordinate base, live clashes and classification completeness.",
  estMinutes: 10,
  steps: [
    {
      id: "base",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.model_quality_audit_before_issue.step.base.in.model",
          label: "Discipline model",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.base.in.origin",
          label: "Shared origin and grid",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.base.out.aligned",
          label: "Origin-aligned model",
        },
        {
          labelKey: "cases.model_quality_audit_before_issue.step.base.out.base",
          label: "Confirmed coordinate base",
        },
      ],
      titleKey: "cases.model_quality_audit_before_issue.step.base.title",
      titleDefault: "Check the coordinate base",
      whatKey: "cases.model_quality_audit_before_issue.step.base.what",
      whatDefault:
        "Confirm the model sits on the shared project origin and grid before anyone downstream measures or clashes against it.",
      whyKey: "cases.model_quality_audit_before_issue.step.base.why",
      whyDefault:
        "A model that is a few centimetres off the shared base silently corrupts every clash test and quantity taken from it later.",
      moduleLabel: "Federations",
      moduleLabelKey: "nav.federations",
      to: "/bim/federations",
    },
    {
      id: "clash",
      icon: "Crosshair",
      inputs: [
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.clash.in.model",
          label: "Origin-aligned model",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.clash.in.rules",
          label: "Clash rule set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.clash.out.results",
          label: "Clash results",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.clash.out.errors",
          label: "Geometry error list",
        },
      ],
      titleKey: "cases.model_quality_audit_before_issue.step.clash.title",
      titleDefault: "Run a clash pass as a quality check",
      whatKey: "cases.model_quality_audit_before_issue.step.clash.what",
      whatDefault:
        "Run the clash test as a final quality gate rather than a coordination exercise, looking specifically for gross geometry errors rather than genuine trade conflicts.",
      whyKey: "cases.model_quality_audit_before_issue.step.clash.why",
      whyDefault:
        "A clash run at issue time catches a model with parts floating in space or duplicated by accident, the kind of error a design review alone can miss.",
      moduleLabel: "Clash detection",
      moduleLabelKey: "nav.clash",
      to: "/clash",
    },
    {
      id: "classify",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.classify.in.model",
          label: "Checked model",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.classify.in.standard",
          label: "Classification standard",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.classify.in.props",
          label: "Required property set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.classify.out.report",
          label: "Validation report",
        },
        {
          labelKey:
            "cases.model_quality_audit_before_issue.step.classify.out.ready",
          label: "Issue-ready model",
        },
      ],
      titleKey: "cases.model_quality_audit_before_issue.step.classify.title",
      titleDefault: "Confirm classification is complete",
      whatKey: "cases.model_quality_audit_before_issue.step.classify.what",
      whatDefault:
        "Run the validation rules and confirm every element carries the classification and property set the next stage expects, with no unmapped category left behind.",
      whyKey: "cases.model_quality_audit_before_issue.step.classify.why",
      whyDefault:
        "A model with a gap in its classification hands the next user, an estimator or a contractor, an element they cannot price or schedule without asking you first.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
  ],
};

export default playbook;
