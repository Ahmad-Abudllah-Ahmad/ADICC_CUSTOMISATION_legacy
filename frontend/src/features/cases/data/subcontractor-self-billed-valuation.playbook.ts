// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Submit a subcontractor valuation and get paid".
//
// The subcontractor side of the payment cycle: value your own work against
// the agreed schedule of values, submit it the moment the cycle opens and
// chase it through to cash in the account. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "subcontractor-self-billed-valuation",
  order: 215,
  category: "commercial",
  companyTypes: ["subcontractor", "cost-consultant", "general-contractor"],
  icon: "Banknote",
  titleKey: "cases.subcontractor_self_billed_valuation.title",
  titleDefault: "Submit a subcontractor valuation and get paid",
  descKey: "cases.subcontractor_self_billed_valuation.desc",
  descDefault:
    "Value your own work against the agreed schedule of values, submit it the moment the cycle opens with the evidence behind it, and chase it through to cash in the account.",
  estMinutes: 10,
  steps: [
    {
      id: "schedule",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.schedule.in.subcontract",
          label: "Signed subcontract",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.schedule.in.sov",
          label: "Schedule of values",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.schedule.out.lines",
          label: "Confirmed line values",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.schedule.out.claimed",
          label: "Claimed-to-date percent",
        },
      ],
      titleKey: "cases.subcontractor_self_billed_valuation.step.schedule.title",
      titleDefault: "Check the schedule of values",
      whatKey: "cases.subcontractor_self_billed_valuation.step.schedule.what",
      whatDefault:
        "Open the subcontract and confirm the schedule of values and the percentage each line is claimed against, so your valuation is built on the same ruler the contractor will measure it with.",
      whyKey: "cases.subcontractor_self_billed_valuation.step.schedule.why",
      whyDefault:
        "A valuation pitched against your own idea of the split, not the agreed schedule, gets cut back before it is even discussed.",
      moduleLabel: "Contracts",
      moduleLabelKey: "onboarding.mod_contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "value",
      icon: "ReceiptText",
      inputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.value.in.lines",
          label: "Confirmed schedule lines",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.value.in.evidence",
          label: "Photos and daywork sheets",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.value.out.valuation",
          label: "Submitted valuation",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.value.out.claim",
          label: "Percentage-complete claim",
        },
      ],
      titleKey: "cases.subcontractor_self_billed_valuation.step.value.title",
      titleDefault: "Submit the valuation",
      whatKey: "cases.subcontractor_self_billed_valuation.step.value.what",
      whatDefault:
        "Assess the percentage complete on each schedule line for this cycle, attach photos and daywork sheets as evidence, and submit the valuation the day the cycle opens.",
      whyKey: "cases.subcontractor_self_billed_valuation.step.value.why",
      whyDefault:
        "Submitting early and with evidence attached is what gets a valuation certified in full instead of chased down to a lower number under time pressure.",
      moduleLabel: "Contracts",
      moduleLabelKey: "onboarding.mod_contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "track",
      icon: "Scale",
      inputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.track.in.valuation",
          label: "Submitted valuation",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.track.in.certificate",
          label: "Payment certificate",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.track.out.reconciled",
          label: "Reconciled payment",
        },
        {
          labelKey:
            "cases.subcontractor_self_billed_valuation.step.track.out.shortfall",
          label: "Flagged shortfall",
        },
      ],
      titleKey: "cases.subcontractor_self_billed_valuation.step.track.title",
      titleDefault: "Track it to paid",
      whatKey: "cases.subcontractor_self_billed_valuation.step.track.what",
      whatDefault:
        "Watch the valuation through certified and paid, and reconcile what actually lands in the account against what you submitted, chasing any shortfall while the backup is still fresh.",
      whyKey: "cases.subcontractor_self_billed_valuation.step.track.why",
      whyDefault:
        "A certified valuation is not cash until it clears, and a quiet under-payment left unreconciled never comes back on its own.",
      moduleLabel: "Reconciliation",
      moduleLabelKey: "nav.reconciliation",
      to: "/projects/:projectId/reconciliation",
    },
  ],
};

export default playbook;
