// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Respond to an invitation to tender as a subcontractor".
//
// Turn an invitation to tender into a clean bid: read the scope and conditions,
// price your package off the bill, and submit a complete return on time.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "respond-to-an-invitation-to-tender-as-a-subcontractor",
  order: 288,
  category: "tendering",
  companyTypes: ["subcontractor"],
  icon: "Send",
  titleKey: "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.title",
  titleDefault: "Respond to an invitation to tender as a subcontractor",
  descKey: "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.desc",
  descDefault:
    "Turn an invitation to tender into a clean bid: read the scope and the conditions, price your package off the bill, and submit a complete return on time.",
  longDescKey:
    "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.longdesc",
  longDescDefault:
    "A rushed tender return with a gap in it either loses the job or wins it at a price that hurts. This case reads the invitation for scope and the conditions that carry risk, prices your package straight off the tender bill so nothing is missed, and packages a complete, on-time submission so you compete on your number rather than on a technicality.",
  estMinutes: 8,
  steps: [
    {
      id: "review",
      icon: "Gavel",
      inputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.in.itt",
          label: "Invitation to tender",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.in.conditions",
          label: "Contract conditions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.out.scope",
          label: "Scope summary",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.out.risk",
          label: "Risk and exclusions",
        },
      ],
      titleKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.title",
      titleDefault: "Read the invitation and the risk",
      whatKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.what",
      whatDefault:
        "Work through the invitation to fix exactly what is in your package and what is not, and flag the conditions that carry risk, from programme to payment terms, before you spend a day pricing.",
      whyKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.review.why",
      whyDefault:
        "A price built on a misread scope is a price you will regret winning. Pinning the scope and the risky terms first is what keeps your bid aimed at the right work and your exclusions clear.",
      moduleLabel: "Bid management",
      moduleLabelKey: "nav.bid_management",
      to: "/bid-management",
    },
    {
      id: "price",
      icon: "Table2",
      inputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.in.bill",
          label: "Tender bill",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.in.scope",
          label: "Scope summary",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.out.priced",
          label: "Priced package",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.out.qualifications",
          label: "Qualifications",
        },
      ],
      titleKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.title",
      titleDefault: "Price your package off the bill",
      whatKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.what",
      whatDefault:
        "Price each line of your package off the tender bill with your rates, note where your quote is qualified, and check the quantities against your own take so you are not pricing someone else's error.",
      whyKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.price.why",
      whyDefault:
        "Pricing straight off the tender bill is what keeps your return line-for-line comparable with the enquiry. Checking the quantities is what stops you inheriting an undermeasure that eats your margin on site.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "submit",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.in.priced",
          label: "Priced package",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.in.documents",
          label: "Required documents",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.out.return",
          label: "Complete tender return",
        },
        {
          labelKey:
            "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.out.record",
          label: "Submission record",
        },
      ],
      titleKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.title",
      titleDefault: "Package and submit on time",
      whatKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.what",
      whatDefault:
        "Assemble the priced return with the qualifications and the documents the enquiry asked for, check nothing is missing, and submit before the deadline with the submission logged.",
      whyKey:
        "cases.respond_to_an_invitation_to_tender_as_a_subcontractor.step.submit.why",
      whyDefault:
        "A strong price in an incomplete return still gets you disqualified. Packaging the full submission and getting it in on time is what puts your number in front of the buyer at all.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
