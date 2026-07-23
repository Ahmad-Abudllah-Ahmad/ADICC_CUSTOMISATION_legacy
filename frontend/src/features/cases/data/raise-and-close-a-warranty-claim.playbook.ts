// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Raise and close a warranty claim".
//
// Get a failed asset fixed on the maker's coin: confirm the cover, raise the
// claim against the asset with evidence, and close it on a clean paper trail.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "raise-and-close-a-warranty-claim",
  order: 274,
  category: "handover",
  companyTypes: ["owner-operator"],
  stage: "operate",
  icon: "ShieldCheck",
  titleKey: "cases.raise_and_close_a_warranty_claim.title",
  titleDefault: "Raise and close a warranty claim",
  descKey: "cases.raise_and_close_a_warranty_claim.desc",
  descDefault:
    "Get a failed asset fixed on the maker's coin: confirm it is in warranty, raise the claim against the asset, and close it once the remedy and the paper trail are in.",
  longDescKey: "cases.raise_and_close_a_warranty_claim.longdesc",
  longDescDefault:
    "A defect fixed out of your own budget when it was still under warranty is money you never get back. This case checks the warranty on the asset first, raises the claim with the fault evidence attached, and keeps the correspondence so the maker's obligation and their response are on the record from first notice to sign-off.",
  estMinutes: 7,
  steps: [
    {
      id: "asset",
      icon: "Boxes",
      inputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.asset.in.asset",
          label: "Failed asset",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.asset.in.terms",
          label: "Warranty terms",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.asset.out.status",
          label: "Warranty status",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.asset.out.eligibility",
          label: "Claim eligibility",
        },
      ],
      titleKey: "cases.raise_and_close_a_warranty_claim.step.asset.title",
      titleDefault: "Confirm the asset is in warranty",
      whatKey: "cases.raise_and_close_a_warranty_claim.step.asset.what",
      whatDefault:
        "Open the asset record, find the install date and the warranty period, and confirm the failure falls inside cover and inside the terms. Pull the serial and model while you are there.",
      whyKey: "cases.raise_and_close_a_warranty_claim.step.asset.why",
      whyDefault:
        "Raising a claim on an asset that is out of cover just wastes everyone's time. Checking the record first tells you in seconds whether the maker owes you a fix or whether this one is on you.",
      moduleLabel: "Assets",
      moduleLabelKey: "nav.assets",
      to: "/assets",
    },
    {
      id: "claim",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.claim.in.status",
          label: "Warranty status",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.claim.in.evidence",
          label: "Fault evidence",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.claim.out.claim",
          label: "Logged warranty claim",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.claim.out.remedy",
          label: "Remedy request",
        },
      ],
      titleKey: "cases.raise_and_close_a_warranty_claim.step.claim.title",
      titleDefault: "Raise the claim with evidence",
      whatKey: "cases.raise_and_close_a_warranty_claim.step.claim.what",
      whatDefault:
        "Raise the claim against the asset with the fault described, photos attached and the warranty reference quoted, and state the remedy you expect. Set a date you need it resolved by.",
      whyKey: "cases.raise_and_close_a_warranty_claim.step.claim.why",
      whyDefault:
        "A claim with the evidence and the reference attached is one the maker cannot bounce back for more detail. Logging it against the asset also keeps the failure in that unit's history for the next time.",
      moduleLabel: "Service",
      moduleLabelKey: "nav.service",
      to: "/projects/:projectId/service",
    },
    {
      id: "notice",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.notice.in.response",
          label: "Maker response",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.notice.in.remedy",
          label: "Completed remedy",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.notice.out.acceptance",
          label: "Formal acceptance",
        },
        {
          labelKey:
            "cases.raise_and_close_a_warranty_claim.step.notice.out.closed",
          label: "Closed claim record",
        },
      ],
      titleKey: "cases.raise_and_close_a_warranty_claim.step.notice.title",
      titleDefault: "Close it on a clean paper trail",
      whatKey: "cases.raise_and_close_a_warranty_claim.step.notice.what",
      whatDefault:
        "Record the maker's response and the remedy in the correspondence log, confirm the fix in writing, and close the claim only when the acceptance is captured, not on a phone call alone.",
      whyKey: "cases.raise_and_close_a_warranty_claim.step.notice.why",
      whyDefault:
        "A warranty settled by phone is one you cannot prove when the same part fails again. The written trail is what holds the maker to the remedy and what backs you if the dispute reopens.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "correspondence.title",
      to: "/projects/:projectId/correspondence",
    },
  ],
};

export default playbook;
