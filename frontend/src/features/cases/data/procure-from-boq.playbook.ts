// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Procure materials from the BOQ".
//
// Turns priced bill positions into purchase orders: pull the quantities you
// need, raise a requisition, order from a supplier and receive against it.
// Content strings are key plus inline English default, kept only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "procure-from-boq",
  order: 25,
  category: "tendering",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "PackageCheck",
  titleKey: "cases.procure_from_boq.title",
  titleDefault: "Procure materials from the BOQ",
  descKey: "cases.procure_from_boq.desc",
  descDefault:
    "Buy the quantities you already priced: raise a requisition off the bill, place the order with a supplier and book the goods in on site.",
  longDescKey: "cases.procure_from_boq.longdesc",
  longDescDefault:
    "This case joins your estimate to real spend without re-keying a single quantity. You start from the priced bill, tick the material lines you are ready to buy, and their quantities flow straight into a purchase requisition for approval. The approved requisition becomes a purchase order to a chosen supplier at an agreed price, and when the delivery lands you book the goods in against that order. Because every step carries the same lines and figures, procurement stays pinned to the budget from the first click to the goods received note, and any drift between what was priced and what was bought shows up straight away rather than months later at the final account.",
  estMinutes: 10,
  next: ["run-a-three-way-match-before-paying-a-supplier"],
  related: [
    "tender-from-boq",
    "issue-a-procurement-and-buying-schedule",
    "maintain-supplier-catalogs-and-buy-from-them",
  ],
  steps: [
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.procure_from_boq.step.boq.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey: "cases.procure_from_boq.step.boq.in.positions",
          label: "Material positions",
        },
      ],
      outputs: [
        {
          labelKey: "cases.procure_from_boq.step.boq.out.selected",
          label: "Selected positions",
        },
        {
          labelKey: "cases.procure_from_boq.step.boq.out.quantities",
          label: "Order quantities",
        },
      ],
      titleKey: "cases.procure_from_boq.step.boq.title",
      titleDefault: "Pick the positions to buy",
      whatKey: "cases.procure_from_boq.step.boq.what",
      whatDefault:
        "Open the bill and tick the positions whose materials you are ready to order. Their quantities flow straight into the requisition, so you buy what was priced rather than a fresh back-of-envelope figure.",
      whyKey: "cases.procure_from_boq.step.boq.why",
      whyDefault:
        "Ordering off the estimate keeps every purchase pinned to the budget. Any drift between what was priced and what gets bought shows the moment it happens, not months later at the final account.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "requisition",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey: "cases.procure_from_boq.step.requisition.in.positions",
          label: "Selected positions",
        },
        {
          labelKey: "cases.procure_from_boq.step.requisition.in.dates",
          label: "Required-by dates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.procure_from_boq.step.requisition.out.requisition",
          label: "Purchase requisition",
        },
        {
          labelKey: "cases.procure_from_boq.step.requisition.out.approval",
          label: "Approval request",
        },
      ],
      titleKey: "cases.procure_from_boq.step.requisition.title",
      titleDefault: "Raise the requisition",
      whatKey: "cases.procure_from_boq.step.requisition.what",
      whatDefault:
        "In Procurement, raise a requisition from those positions and route it for approval. It captures what is needed, in what quantity and by when it must be on site.",
      whyKey: "cases.procure_from_boq.step.requisition.why",
      whyDefault:
        "The requisition is the controlled step between a site need and committed spend. It gives the buyer and the approver a single document to check, so nothing gets ordered on a verbal say-so.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
    {
      id: "order",
      icon: "Send",
      inputs: [
        {
          labelKey: "cases.procure_from_boq.step.order.in.requisition",
          label: "Approved requisition",
        },
        {
          labelKey: "cases.procure_from_boq.step.order.in.supplier",
          label: "Supplier catalogue",
        },
      ],
      outputs: [
        {
          labelKey: "cases.procure_from_boq.step.order.out.po",
          label: "Purchase order",
        },
        {
          labelKey: "cases.procure_from_boq.step.order.out.delivery",
          label: "Delivery date",
        },
      ],
      titleKey: "cases.procure_from_boq.step.order.title",
      titleDefault: "Order from a supplier",
      whatKey: "cases.procure_from_boq.step.order.what",
      whatDefault:
        "Convert the approved requisition into a purchase order, choose the supplier and their catalogue price, and issue it. The order carries the lines, the agreed prices and the delivery date.",
      whyKey: "cases.procure_from_boq.step.order.why",
      whyDefault:
        "A purchase order is a legal commitment, not a wish list. Raising it from the requisition keeps quantities and prices consistent all the way from estimate to spend, with no silent edits in between.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
    {
      id: "receive",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey: "cases.procure_from_boq.step.receive.in.po",
          label: "Open purchase order",
        },
        {
          labelKey: "cases.procure_from_boq.step.receive.in.goods",
          label: "Delivered goods",
        },
      ],
      outputs: [
        {
          labelKey: "cases.procure_from_boq.step.receive.out.grn",
          label: "Goods received note",
        },
        {
          labelKey: "cases.procure_from_boq.step.receive.out.flags",
          label: "Delivery discrepancy flags",
        },
      ],
      titleKey: "cases.procure_from_boq.step.receive.title",
      titleDefault: "Receive against the order",
      whatKey: "cases.procure_from_boq.step.receive.what",
      whatDefault:
        "When the lorry arrives, book in what physically turned up against the order. Short loads and over deliveries are flagged straight away so the invoice can be checked against goods actually received.",
      whyKey: "cases.procure_from_boq.step.receive.why",
      whyDefault:
        "Receiving joins the dots between ordered, delivered and invoiced. It is the check that means you pay for what landed on site and catch the wrong or short delivery before finance settles it.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
  ],
};

export default playbook;
