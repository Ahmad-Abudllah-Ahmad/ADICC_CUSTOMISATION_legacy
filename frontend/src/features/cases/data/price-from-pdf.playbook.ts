// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Price a building from a PDF".
//
// The reference playbook. It walks a user from a raw PDF drawing all the way to
// a priced, validated estimate they can export, crossing five modules in the
// order a real estimator works them. Every content string is a key plus an
// inline English default - these stay HERE and are never added to en.ts (only
// the framework chrome lives there). Module chips reuse existing translated
// nav/title keys so they localize for free.
//
// To add another case, copy this file to ./<slug>.playbook.ts, give it a fresh
// id and a new `order`, and default-export it. It is picked up automatically.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "price-from-pdf",
  order: 10,
  category: "estimating",
  companyTypes: ["general-contractor", "subcontractor", "cost-consultant"],
  icon: "FileSpreadsheet",
  titleKey: "cases.price_from_pdf.title",
  titleDefault: "Price a building from a PDF",
  descKey: "cases.price_from_pdf.desc",
  descDefault:
    "Start from a flat PDF drawing and finish with a priced, validated estimate ready to export. You measure it, price it, check it and hand it on. Five steps, end to end.",
  estMinutes: 15,
  steps: [
    {
      id: "upload",
      icon: "Upload",
      inputs: [
        {
          labelKey: "cases.price_from_pdf.step.upload.in.pdf",
          label: "PDF drawing",
        },
        {
          labelKey: "cases.price_from_pdf.step.upload.in.project",
          label: "Project record",
        },
      ],
      outputs: [
        {
          labelKey: "cases.price_from_pdf.step.upload.out.filed",
          label: "Filed drawing",
        },
        {
          labelKey: "cases.price_from_pdf.step.upload.out.linked",
          label: "Linked to project",
        },
      ],
      titleKey: "cases.price_from_pdf.step.upload.title",
      titleDefault: "Upload the PDF drawing",
      whatKey: "cases.price_from_pdf.step.upload.what",
      whatDefault:
        "Open the project files area and drag the PDF plan you intend to price onto it. The drawing is filed against the project so takeoff, pricing and every export can reach the exact same sheet.",
      whyKey: "cases.price_from_pdf.step.upload.why",
      whyDefault:
        "Every number downstream traces back to this one drawing. Filing it against the project up front keeps the measurement, the bill and the outputs locked to a single revision rather than scattered copies.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.project_files",
      to: "/projects/:projectId/files",
    },
    {
      id: "takeoff",
      icon: "Ruler",
      inputs: [
        {
          labelKey: "cases.price_from_pdf.step.takeoff.in.drawing",
          label: "Filed PDF drawing",
        },
        {
          labelKey: "cases.price_from_pdf.step.takeoff.in.scale",
          label: "Set drawing scale",
        },
      ],
      outputs: [
        {
          labelKey: "cases.price_from_pdf.step.takeoff.out.quantities",
          label: "Measured quantities",
        },
        {
          labelKey: "cases.price_from_pdf.step.takeoff.out.markups",
          label: "Takeoff markups",
        },
      ],
      titleKey: "cases.price_from_pdf.step.takeoff.title",
      titleDefault: "Measure quantities on the PDF",
      whatKey: "cases.price_from_pdf.step.takeoff.what",
      whatDefault:
        "Open the sheet in Takeoff and set the scale first, then measure the areas, running lengths and counts you need. Let auto-measure pick up repeated items like doors and columns, and eyeball each one before you accept it.",
      whyKey: "cases.price_from_pdf.step.takeoff.why",
      whyDefault:
        "Quantities carry the whole estimate, so a slip here multiplies through every rate. Measuring on the drawing itself means each figure points back to a line you can show the client, not a number from thin air.",
      moduleLabel: "Takeoff",
      moduleLabelKey: "nav.pdf_measurements",
      to: "/takeoff?tab=measurements",
    },
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.price_from_pdf.step.boq.in.quantities",
          label: "Measured quantities",
        },
        {
          labelKey: "cases.price_from_pdf.step.boq.in.rates",
          label: "Cost database rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.price_from_pdf.step.boq.out.boq",
          label: "Priced BOQ",
        },
        {
          labelKey: "cases.price_from_pdf.step.boq.out.total",
          label: "Estimate total",
        },
      ],
      titleKey: "cases.price_from_pdf.step.boq.title",
      titleDefault: "Build the priced BOQ",
      whatKey: "cases.price_from_pdf.step.boq.what",
      whatDefault:
        "Send the measured quantities into bill positions, then attach unit rates from the cost database or your own assemblies. The total updates the moment a rate lands.",
      whyKey: "cases.price_from_pdf.step.boq.why",
      whyDefault:
        "The bill of quantities is where the drawing turns into money. Rates and built-up assemblies roll into a total you can break down line by line and defend across a negotiating table.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
    {
      id: "validate",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.price_from_pdf.step.validate.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey: "cases.price_from_pdf.step.validate.in.rules",
          label: "Validation rule sets",
        },
      ],
      outputs: [
        {
          labelKey: "cases.price_from_pdf.step.validate.out.report",
          label: "Traffic-light report",
        },
        {
          labelKey: "cases.price_from_pdf.step.validate.out.issues",
          label: "Flagged issues",
        },
      ],
      titleKey: "cases.price_from_pdf.step.validate.title",
      titleDefault: "Validate the estimate",
      whatKey: "cases.price_from_pdf.step.validate.what",
      whatDefault:
        "Run the rule sets across the finished bill. It hunts for blank quantities, zero rates and duplicate lines, and where they apply it checks structure rules such as the DIN 276 cost groups.",
      whyKey: "cases.price_from_pdf.step.validate.why",
      whyDefault:
        "A mistake caught at your desk costs minutes; the same mistake caught by the client costs credibility. The traffic-light report points straight at the line and the rule that tripped.",
      moduleLabel: "Validation",
      moduleLabelKey: "validation.title",
      to: "/validation",
    },
    {
      id: "export",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.price_from_pdf.step.export.in.boq",
          label: "Validated BOQ",
        },
        {
          labelKey: "cases.price_from_pdf.step.export.in.format",
          label: "Chosen export format",
        },
      ],
      outputs: [
        {
          labelKey: "cases.price_from_pdf.step.export.out.pdf",
          label: "PDF summary",
        },
        {
          labelKey: "cases.price_from_pdf.step.export.out.file",
          label: "Excel or GAEB file",
        },
      ],
      titleKey: "cases.price_from_pdf.step.export.title",
      titleDefault: "Export the priced bill",
      whatKey: "cases.price_from_pdf.step.export.what",
      whatDefault:
        "Produce the output the next person needs from Reports: a PDF summary for the client, an Excel sheet for the commercial team or a GAEB file to push into tendering.",
      whyKey: "cases.price_from_pdf.step.export.why",
      whyDefault:
        "An estimate only pays off once somebody else can open it. Exporting to an open format keeps the figures portable between tools and keeps the underlying data yours.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
