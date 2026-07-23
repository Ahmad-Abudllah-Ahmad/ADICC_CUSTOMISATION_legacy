// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a delay and disruption claim with evidence".
//
// Open the claim under the right contract clause, pull the site diary records
// that prove the event and its effect, tie in the change history that drove it,
// then assemble a substantiated narrative and value in one report.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-a-delay-and-disruption-claim-with-evidence",
  order: 326,
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "Scale",
  titleKey: "cases.build_a_delay_and_disruption_claim_with_evidence.title",
  titleDefault: "Build a delay and disruption claim with evidence",
  descKey: "cases.build_a_delay_and_disruption_claim_with_evidence.desc",
  descDefault:
    "Open the claim under the right contract clause, pull the site diary records that prove the event and its effect, tie in the change history that drove it, then assemble a substantiated narrative and value in one report.",
  estMinutes: 12,
  steps: [
    {
      id: "open",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.in.contract",
          label: "Contract terms",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.in.clause",
          label: "Entitlement clause",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.in.event",
          label: "Triggering event",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.out.claim",
          label: "Opened claim",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.out.notice",
          label: "Notice of claim",
        },
      ],
      titleKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.title",
      titleDefault: "Open the claim under the clause",
      whatKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.what",
      whatDefault:
        "Open a claim against the contract, citing the specific clause that gives the entitlement and the event that triggered it, with the dates and notice requirements set out.",
      whyKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.open.why",
      whyDefault:
        "A claim with no clause behind it is just a complaint. Anchoring it to the right provision, and to the notice the contract demands, is what makes it an entitlement the other side has to answer.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "evidence",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.in.diary",
          label: "Site diary entries",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.in.returns",
          label: "Labour & plant returns",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.in.photos",
          label: "Site photos",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.out.record",
          label: "Contemporaneous record",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.out.timeline",
          label: "Evidence timeline",
        },
      ],
      titleKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.title",
      titleDefault: "Pull the site evidence",
      whatKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.what",
      whatDefault:
        "Pull the diary entries, labour and plant returns and photos that show the event happened, when it happened, and how it stopped or slowed the work on the ground.",
      whyKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.evidence.why",
      whyDefault:
        "Delay argued from memory gets argued down. Contemporaneous site records are the difference between a claim that gets paid and an assertion the other side simply denies.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "link",
      icon: "LineChart",
      inputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.in.changes",
          label: "Change instructions",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.in.activities",
          label: "Affected activities",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.in.record",
          label: "Site record",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.out.chain",
          label: "Cause-and-effect chain",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.out.slip",
          label: "Quantified programme slip",
        },
      ],
      titleKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.title",
      titleDefault: "Link the change history",
      whatKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.what",
      whatDefault:
        "Tie in the changes and instructions that drove the delay, showing the chain from the event through the affected activities to the programme slip.",
      whyKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.link.why",
      whyDefault:
        "A big number with nothing behind it invites a fight. Linking each day of delay back to the change that caused it is what turns a round figure into a substantiated cause and effect.",
      moduleLabel: "Change intelligence",
      moduleLabelKey: "nav.change_intelligence",
      to: "/change-intelligence",
    },
    {
      id: "assemble",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.in.narrative",
          label: "Claim narrative",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.in.evidence",
          label: "Evidence bundle",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.in.chain",
          label: "Cause-and-effect chain",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.out.report",
          label: "Substantiated claim report",
        },
        {
          labelKey:
            "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.out.value",
          label: "Time and money claimed",
        },
      ],
      titleKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.title",
      titleDefault: "Assemble the claim",
      whatKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.what",
      whatDefault:
        "Pull the clause, the records and the change chain into one claim document that sets out the narrative, the entitlement and the time and money being sought.",
      whyKey:
        "cases.build_a_delay_and_disruption_claim_with_evidence.step.assemble.why",
      whyDefault:
        "A claim scattered across emails and folders never gets read, let alone paid. One assembled, evidenced narrative is what a client, an adjudicator or a court can actually assess and agree.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
