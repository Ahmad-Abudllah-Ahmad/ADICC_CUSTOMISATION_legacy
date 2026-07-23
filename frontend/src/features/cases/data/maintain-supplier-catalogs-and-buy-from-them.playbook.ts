// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Maintain supplier catalogs and buy from them".
//
// Keep each supplier price list current, raise the project buying schedule
// against those live rates, then report committed spend back against the
// estimate allowance. Content strings are key plus inline English default and
// live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "maintain-supplier-catalogs-and-buy-from-them",
  order: 328,
  category: "tendering",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "Database",
  titleKey: "cases.maintain_supplier_catalogs_and_buy_from_them.title",
  titleDefault: "Maintain supplier catalogs and buy from them",
  descKey: "cases.maintain_supplier_catalogs_and_buy_from_them.desc",
  descDefault:
    "Import and keep your supplier price lists current, raise the project buying schedule against those live rates, and report committed spend against the estimate allowance so nothing quietly buys over budget.",
  estMinutes: 9,
  steps: [
    {
      id: "catalogs",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.in.pricelists",
          label: "Supplier price lists",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.in.updates",
          label: "New price updates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.out.catalog",
          label: "Live supplier catalogs",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.out.rates",
          label: "Current buying rates",
        },
      ],
      titleKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.title",
      titleDefault: "Import and update supplier catalogs",
      whatKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.what",
      whatDefault:
        "Import each supplier price list into its own catalog and refresh it whenever new prices land, so the rates you buy against are the ones the supplier is quoting today.",
      whyKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.catalogs.why",
      whyDefault:
        "Buying off a stale price list is how a package lands over budget before a single order goes out. A current catalog keeps the estimate and the order working from the same numbers.",
      moduleLabel: "Supplier Catalogs",
      to: "/supplier-catalogs",
    },
    {
      id: "buy",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.in.catalogs",
          label: "Live supplier catalogs",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.in.packages",
          label: "Package scope",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.out.schedule",
          label: "Priced buying schedule",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.out.orders",
          label: "Committed orders",
        },
      ],
      titleKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.title",
      titleDefault: "Raise the buying schedule",
      whatKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.what",
      whatDefault:
        "Build the project buying schedule and price each package straight off the live supplier catalogs, so every line carries a real quoted rate rather than a guessed allowance.",
      whyKey: "cases.maintain_supplier_catalogs_and_buy_from_them.step.buy.why",
      whyDefault:
        "Pricing the buy against the actual catalog turns a rough allowance into a committed number you can hold the supplier to, and it flags any item where the market has moved since the estimate.",
      moduleLabel: "Procurement",
      to: "/projects/:projectId/procurement",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.in.orders",
          label: "Placed orders",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.in.allowance",
          label: "Estimate allowances",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.out.report",
          label: "Committed spend report",
        },
        {
          labelKey:
            "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.out.flags",
          label: "Over-budget flags",
        },
      ],
      titleKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.title",
      titleDefault: "Report committed spend vs allowance",
      whatKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.what",
      whatDefault:
        "Pull the committed-cost report and set the orders you have placed against the allowance carried in the estimate, package by package.",
      whyKey:
        "cases.maintain_supplier_catalogs_and_buy_from_them.step.report.why",
      whyDefault:
        "Knowing early which packages are buying over their allowance is what lets you claw the money back elsewhere while there is still budget to move, not at final account.",
      moduleLabel: "Reports",
      to: "/reports",
    },
  ],
};

export default playbook;
