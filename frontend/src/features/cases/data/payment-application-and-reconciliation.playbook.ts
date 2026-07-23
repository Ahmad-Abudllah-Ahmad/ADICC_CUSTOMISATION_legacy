// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Payment application and reconciliation".
//
// Value the work done this period against the contract, raise the payment
// application and reconcile what was certified against what was paid. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "payment-application-and-reconciliation",
  order: 110,
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "Receipt",
  titleKey: "cases.payment_application_and_reconciliation.title",
  titleDefault: "Payment application and reconciliation",
  descKey: "cases.payment_application_and_reconciliation.desc",
  descDefault:
    "Value the work put in place this period against the contract, raise the application with the evidence behind it, and reconcile what you certified against what actually landed in the account.",
  estMinutes: 12,
  steps: [
    {
      id: "contract",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.contract.in.contract",
          label: "Signed contract",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.contract.in.variations",
          label: "Agreed variations",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.contract.in.terms",
          label: "Retention & terms",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.contract.out.sum",
          label: "Confirmed contract sum",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.contract.out.base",
          label: "Current entitlement base",
        },
      ],
      titleKey:
        "cases.payment_application_and_reconciliation.step.contract.title",
      titleDefault: "Confirm the contract position",
      whatKey:
        "cases.payment_application_and_reconciliation.step.contract.what",
      whatDefault:
        "Confirm the current contract sum, every agreed variation and the retention and payment terms, so the application is built on the number both sides have actually signed up to.",
      whyKey: "cases.payment_application_and_reconciliation.step.contract.why",
      whyDefault:
        "An application worked off a stale figure, before the agreed variations went in, gets kicked straight back. Starting from the true contract position is what gets it certified without a fight.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "apply",
      icon: "Banknote",
      inputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.apply.in.sum",
          label: "Confirmed contract sum",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.apply.in.work",
          label: "Work done this cycle",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.apply.in.materials",
          label: "Materials on site",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.apply.out.application",
          label: "Payment application",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.apply.out.evidence",
          label: "Supporting evidence",
        },
      ],
      titleKey: "cases.payment_application_and_reconciliation.step.apply.title",
      titleDefault: "Raise the payment application",
      whatKey: "cases.payment_application_and_reconciliation.step.apply.what",
      whatDefault:
        "Measure the work done this cycle, add materials properly on site and approved variations, then deduct retention and everything previously paid before you issue the application.",
      whyKey: "cases.payment_application_and_reconciliation.step.apply.why",
      whyDefault:
        "Cash flow is the oxygen of a construction business, and subcontractors feel a late certificate first. An application that is clear and fully evidenced is the one that gets signed on the due date.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "reconcile",
      icon: "Scale",
      inputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.reconcile.in.application",
          label: "Payment application",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.reconcile.in.certificate",
          label: "Payment certificate",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.reconcile.in.remittance",
          label: "Remittance received",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.reconcile.out.reconciled",
          label: "Reconciled position",
        },
        {
          labelKey:
            "cases.payment_application_and_reconciliation.step.reconcile.out.claims",
          label: "Shortfall claims",
        },
      ],
      titleKey:
        "cases.payment_application_and_reconciliation.step.reconcile.title",
      titleDefault: "Reconcile certified against paid",
      whatKey:
        "cases.payment_application_and_reconciliation.step.reconcile.what",
      whatDefault:
        "Line up what you applied for against what the certifier allowed and what was actually paid, then chase every under-certification, wrongly held retention or dropped line.",
      whyKey: "cases.payment_application_and_reconciliation.step.reconcile.why",
      whyDefault:
        "A few percent shaved off each valuation vanishes quietly and never returns by itself. Reconciling every cycle, while the backup is still to hand, is how that money finds its way home.",
      moduleLabel: "Reconciliation",
      moduleLabelKey: "nav.reconciliation",
      to: "/projects/:projectId/reconciliation",
    },
  ],
};

export default playbook;
