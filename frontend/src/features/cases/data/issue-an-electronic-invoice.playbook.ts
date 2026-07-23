// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Issue an electronic invoice".
//
// Turn a certified amount into a compliant electronic invoice, issue it in the
// structured format your client and tax authority accept, then track it to
// paid. Content strings are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "issue-an-electronic-invoice",
  order: 125,
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "ReceiptText",
  titleKey: "cases.issue_an_electronic_invoice.title",
  titleDefault: "Issue an electronic invoice",
  descKey: "cases.issue_an_electronic_invoice.desc",
  descDefault:
    "Turn a certified valuation into a compliant electronic invoice, issue it in the structured format your client and tax authority accept, then track it through to paid and reconciled.",
  estMinutes: 10,
  steps: [
    {
      id: "confirm",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.issue_an_electronic_invoice.step.confirm.in.valuation",
          label: "Certified valuation",
        },
        {
          labelKey:
            "cases.issue_an_electronic_invoice.step.confirm.in.previous",
          label: "Previous invoices",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.confirm.in.tax",
          label: "Tax & reverse-charge rules",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_an_electronic_invoice.step.confirm.out.amount",
          label: "Net amount to invoice",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.confirm.out.tax",
          label: "Confirmed tax treatment",
        },
      ],
      titleKey: "cases.issue_an_electronic_invoice.step.confirm.title",
      titleDefault: "Confirm the amount to invoice",
      whatKey: "cases.issue_an_electronic_invoice.step.confirm.what",
      whatDefault:
        "Take the certified valuation for the period, deduct retention and everything already invoiced, and confirm the tax treatment and any reverse-charge rule that applies to the works.",
      whyKey: "cases.issue_an_electronic_invoice.step.confirm.why",
      whyDefault:
        "An invoice raised for more than was certified gets rejected, and one that mishandles the tax gets bounced by the buyer or the authority. Starting from the agreed figure is what gets it accepted first time.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "issue",
      icon: "Receipt",
      inputs: [
        {
          labelKey: "cases.issue_an_electronic_invoice.step.issue.in.amount",
          label: "Net amount to invoice",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.issue.in.buyer",
          label: "Buyer reference",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.issue.in.format",
          label: "E-invoice standard",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_an_electronic_invoice.step.issue.out.einvoice",
          label: "Structured e-invoice",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.issue.out.sent",
          label: "Delivered to client",
        },
      ],
      titleKey: "cases.issue_an_electronic_invoice.step.issue.title",
      titleDefault: "Issue the electronic invoice",
      whatKey: "cases.issue_an_electronic_invoice.step.issue.what",
      whatDefault:
        "Generate the invoice as a structured electronic document, with the buyer reference, line detail and tax breakdown the standard requires, and send it through the channel your client mandates.",
      whyKey: "cases.issue_an_electronic_invoice.step.issue.why",
      whyDefault:
        "More countries and public clients now refuse a paper or PDF invoice outright and only accept a structured e-invoice. Issuing the compliant format means the invoice is machine-read and booked instead of sitting in a rejection queue.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "track",
      icon: "Scale",
      inputs: [
        {
          labelKey: "cases.issue_an_electronic_invoice.step.track.in.invoice",
          label: "Issued invoice",
        },
        {
          labelKey: "cases.issue_an_electronic_invoice.step.track.in.due",
          label: "Payment due date",
        },
        {
          labelKey:
            "cases.issue_an_electronic_invoice.step.track.in.remittance",
          label: "Remittance received",
        },
      ],
      outputs: [
        {
          labelKey: "cases.issue_an_electronic_invoice.step.track.out.paid",
          label: "Payment received",
        },
        {
          labelKey:
            "cases.issue_an_electronic_invoice.step.track.out.reconciled",
          label: "Reconciled invoice",
        },
      ],
      titleKey: "cases.issue_an_electronic_invoice.step.track.title",
      titleDefault: "Track it to paid",
      whatKey: "cases.issue_an_electronic_invoice.step.track.what",
      whatDefault:
        "Watch the invoice through received, approved and paid, chase anything stuck past its due date, and reconcile the amount that lands against what you issued.",
      whyKey: "cases.issue_an_electronic_invoice.step.track.why",
      whyDefault:
        "An issued invoice is not money until it is paid, and a short payment slips by unnoticed unless you match it back. Tracking every one to settlement is how the cash you earned actually reaches the account.",
      moduleLabel: "Reconciliation",
      moduleLabelKey: "nav.reconciliation",
      to: "/projects/:projectId/reconciliation",
    },
  ],
};

export default playbook;
