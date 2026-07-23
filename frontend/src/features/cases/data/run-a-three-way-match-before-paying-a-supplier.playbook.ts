// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a three-way match before paying a supplier".
//
// Only pay for what you ordered and received: match the invoice to the order and
// the goods received note, resolve the differences, then release the payment.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-three-way-match-before-paying-a-supplier",
  order: 282,
  category: "commercial",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "Scale",
  titleKey: "cases.run_a_three_way_match_before_paying_a_supplier.title",
  titleDefault: "Run a three-way match before paying a supplier",
  descKey: "cases.run_a_three_way_match_before_paying_a_supplier.desc",
  descDefault:
    "Only pay for what you ordered and received: line the invoice up against the purchase order and the goods received note, resolve the differences, then release the payment.",
  longDescKey: "cases.run_a_three_way_match_before_paying_a_supplier.longdesc",
  longDescDefault:
    "Paying a supplier invoice without checking it against the order and the delivery is how a project quietly overpays for goods it never got. This case matches the invoice to the purchase order and the goods received note, holds anything that does not line up until it is explained, and only releases the ones that pass so every payment is for work actually ordered and actually delivered.",
  estMinutes: 8,
  steps: [
    {
      id: "order",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.order.in.po",
          label: "Purchase order",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.order.in.grn",
          label: "Goods received note",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.order.out.ordered",
          label: "Ordered quantities",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.order.out.received",
          label: "Received quantities",
        },
      ],
      titleKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.order.title",
      titleDefault: "Pull the order and the receipt",
      whatKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.order.what",
      whatDefault:
        "Open the purchase order and its goods received note so you have, side by side, what you agreed to buy at what price and what actually turned up on site.",
      whyKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.order.why",
      whyDefault:
        "The invoice is only one of three documents that have to agree. Pulling the order and the receipt first is what gives you something honest to check the supplier's bill against.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
    {
      id: "match",
      icon: "GitCompare",
      inputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.match.in.invoice",
          label: "Supplier invoice",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.match.in.quantities",
          label: "Ordered and received quantities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.match.out.matched",
          label: "Matched lines",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.match.out.flagged",
          label: "Flagged discrepancies",
        },
      ],
      titleKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.match.title",
      titleDefault: "Match the invoice against both",
      whatKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.match.what",
      whatDefault:
        "Line the invoice up against the order and the receipt, pass the lines where price and quantity agree on all three, and flag any short delivery, price creep or item you never ordered.",
      whyKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.match.why",
      whyDefault:
        "A three-way match is the check that catches the invoice for forty units when thirty arrived. Doing it before payment is far cheaper than clawing money back from a supplier afterwards.",
      moduleLabel: "Reconciliation",
      moduleLabelKey: "nav.reconciliation",
      to: "/projects/:projectId/reconciliation",
    },
    {
      id: "pay",
      icon: "Banknote",
      inputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.in.matched",
          label: "Matched lines",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.in.value",
          label: "Approved value",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.out.payment",
          label: "Approved payment",
        },
        {
          labelKey:
            "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.out.held",
          label: "Held queries",
        },
      ],
      titleKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.title",
      titleDefault: "Release only the matched payment",
      whatKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.what",
      whatDefault:
        "Release payment for the lines that matched, hold back the flagged ones until the supplier explains or credits them, and record why anything was held so the query has a trail.",
      whyKey:
        "cases.run_a_three_way_match_before_paying_a_supplier.step.pay.why",
      whyDefault:
        "Paying the whole invoice to avoid the hassle of a query is how the leaks add up. Releasing only what matched keeps the pressure on the supplier to fix their bill and keeps your cost honest.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
  ],
};

export default playbook;
