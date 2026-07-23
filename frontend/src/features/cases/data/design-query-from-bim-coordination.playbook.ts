// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Raise a design query from BIM coordination".
//
// A designer / BIM consultant case: turn a conflict spotted in the federated
// model into a formal design query, get it answered by the right discipline,
// and update the model once the fix lands. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "design-query-from-bim-coordination",
  order: 230,
  category: "bim",
  companyTypes: ["designer", "bim-consultant", "project-manager"],
  icon: "MessageSquare",
  titleKey: "cases.design_query_from_bim_coordination.title",
  titleDefault: "Raise a design query from BIM coordination",
  descKey: "cases.design_query_from_bim_coordination.desc",
  descDefault:
    "Turn a conflict spotted in the federated model into a formal design query, get it answered by the right discipline, and update the model once the fix lands.",
  estMinutes: 10,
  steps: [
    {
      id: "review",
      icon: "Layers",
      inputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.review.in.federation",
          label: "Federated model",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.review.in.flag",
          label: "Coordination flag",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.review.out.conflict",
          label: "Located conflict",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.review.out.discipline",
          label: "Responsible discipline",
        },
      ],
      titleKey: "cases.design_query_from_bim_coordination.step.review.title",
      titleDefault: "Review the federated model",
      whatKey: "cases.design_query_from_bim_coordination.step.review.what",
      whatDefault:
        "Open the federation and look over the area the coordination meeting flagged, checking which discipline model actually needs to change.",
      whyKey: "cases.design_query_from_bim_coordination.step.review.why",
      whyDefault:
        "A query raised against the wrong discipline just bounces back a week later. Confirming the source in the federated view first is what gets it to the right desk the first time.",
      moduleLabel: "Federations",
      moduleLabelKey: "nav.federations",
      to: "/bim/federations",
    },
    {
      id: "query",
      icon: "MessageSquare",
      inputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.query.in.conflict",
          label: "Located conflict",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.query.in.viewpoint",
          label: "Model viewpoint",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.query.in.deadline",
          label: "Answer deadline",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.query.out.rfi",
          label: "Formal design query",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.query.out.tracked",
          label: "Tracked RFI",
        },
      ],
      titleKey: "cases.design_query_from_bim_coordination.step.query.title",
      titleDefault: "Raise the query",
      whatKey: "cases.design_query_from_bim_coordination.step.query.what",
      whatDefault:
        "Raise a formal request naming the element, the model view it was found in and the clash or conflict it causes, with a date tied to when the trade needs the answer.",
      whyKey: "cases.design_query_from_bim_coordination.step.query.why",
      whyDefault:
        "A conflict mentioned in a meeting and never formalised gets forgotten by the next one. A dated, written query is what keeps it moving until it is actually resolved.",
      moduleLabel: "RFIs",
      moduleLabelKey: "nav.rfi",
      to: "/projects/:projectId/rfi",
    },
    {
      id: "update",
      icon: "Box",
      inputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.update.in.answer",
          label: "Query answer",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.update.in.model",
          label: "Affected model",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.update.in.conflict",
          label: "Original conflict",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.update.out.updated",
          label: "Updated model",
        },
        {
          labelKey:
            "cases.design_query_from_bim_coordination.step.update.out.verified",
          label: "Verified fix",
        },
      ],
      titleKey: "cases.design_query_from_bim_coordination.step.update.title",
      titleDefault: "Update the model",
      whatKey: "cases.design_query_from_bim_coordination.step.update.what",
      whatDefault:
        "Once the answer lands, update the affected model and confirm the fix against the original conflict before it is reissued to the team.",
      whyKey: "cases.design_query_from_bim_coordination.step.update.why",
      whyDefault:
        "The query only closes the loop when the model itself reflects the fix. Otherwise the same conflict resurfaces the next time someone federates the set.",
      moduleLabel: "BIM",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
  ],
};

export default playbook;
