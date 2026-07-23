// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get a material submittal approved".
//
// Put a proposed product or material in front of the designer, prove it meets
// the specification, and release it to order only once it is signed off.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "material-submittal-and-approval",
  order: 165,
  category: "quality",
  companyTypes: ["subcontractor", "designer", "general-contractor"],
  icon: "FileCheck",
  titleKey: "cases.material_submittal_and_approval.title",
  titleDefault: "Get a material submittal approved",
  descKey: "cases.material_submittal_and_approval.desc",
  descDefault:
    "Put the product you plan to buy in front of the designer with its data behind it, get it checked against the specification, and release it to order only once it is approved.",
  estMinutes: 9,
  steps: [
    {
      id: "submit",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.submit.in.product",
          label: "Proposed product",
        },
        {
          labelKey: "cases.material_submittal_and_approval.step.submit.in.data",
          label: "Data sheets and certificates",
        },
        {
          labelKey:
            "cases.material_submittal_and_approval.step.submit.in.clause",
          label: "Specification clause",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.submit.out.submittal",
          label: "Routed submittal",
        },
        {
          labelKey:
            "cases.material_submittal_and_approval.step.submit.out.deadline",
          label: "Needed-by date",
        },
      ],
      titleKey: "cases.material_submittal_and_approval.step.submit.title",
      titleDefault: "Raise the submittal",
      whatKey: "cases.material_submittal_and_approval.step.submit.what",
      whatDefault:
        "Open the submittal for the product you intend to use, attach the data sheet, samples and certificates, and name the specification clause it is offered against. Route it to the designer who has to approve it and set a needed-by date tied to when you must order to hit the programme.",
      whyKey: "cases.material_submittal_and_approval.step.submit.why",
      whyDefault:
        "Ordering a material before it is approved is how you end up with a skip full of the wrong product and an argument over who pays. A dated submittal also puts the clock on the designer, so a slow approval that delays your order is on the record.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "review",
      icon: "ClipboardCheck",
      inputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.review.in.submittal",
          label: "Routed submittal",
        },
        {
          labelKey: "cases.material_submittal_and_approval.step.review.in.spec",
          label: "Specification requirements",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.review.out.decision",
          label: "Approval decision",
        },
        {
          labelKey:
            "cases.material_submittal_and_approval.step.review.out.deviations",
          label: "Recorded deviations",
        },
      ],
      titleKey: "cases.material_submittal_and_approval.step.review.title",
      titleDefault: "Check it against the spec",
      whatKey: "cases.material_submittal_and_approval.step.review.what",
      whatDefault:
        "Line the submitted product up against the specified performance, finish and standards, clause by clause, and record the outcome: approved, approved with comments, or rejected with the reason. Log any deviation the designer accepts so it is not queried later.",
      whyKey: "cases.material_submittal_and_approval.step.review.why",
      whyDefault:
        "A checked submittal is the moment a substitution is caught before it is built in, not after. The recorded decision is what protects you when the client asks why the installed product differs from the drawings.",
      moduleLabel: "Quality management",
      moduleLabelKey: "nav.qms",
      to: "/projects/:projectId/qms",
    },
    {
      id: "release",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.release.in.approval",
          label: "Approval decision",
        },
        {
          labelKey:
            "cases.material_submittal_and_approval.step.release.in.product",
          label: "Approved product",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.material_submittal_and_approval.step.release.out.order",
          label: "Purchase order",
        },
        {
          labelKey:
            "cases.material_submittal_and_approval.step.release.out.linked",
          label: "Submittal-linked order",
        },
      ],
      titleKey: "cases.material_submittal_and_approval.step.release.title",
      titleDefault: "Release it to order",
      whatKey: "cases.material_submittal_and_approval.step.release.what",
      whatDefault:
        "Once the submittal is approved, raise the purchase order against the exact product that was signed off, quoting the submittal reference on the order so the yard and the supplier deliver the approved item and nothing else.",
      whyKey: "cases.material_submittal_and_approval.step.release.why",
      whyDefault:
        "The approval only holds value if what turns up on site is the thing that was approved. Tying the order back to the submittal reference is what stops a supplier quietly swapping in a cheaper equivalent.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
  ],
};

export default playbook;
