// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Measure quantities from a DWG".
//
// Open a drawing, measure areas and lengths on it, then carry the measured
// quantities into a priced bill. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "takeoff-from-dwg",
  order: 45,
  category: "bim",
  companyTypes: ["cost-consultant", "general-contractor", "bim-consultant"],
  icon: "Ruler",
  titleKey: "cases.takeoff_from_dwg.title",
  titleDefault: "Measure quantities from a DWG",
  descKey: "cases.takeoff_from_dwg.desc",
  descDefault:
    "Load a DWG, lock the scale against a known dimension, measure the areas, lengths and counts you need, then push those quantities straight into a priced bill.",
  estMinutes: 10,
  steps: [
    {
      id: "open",
      icon: "Ruler",
      inputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.open.in.dwg",
          label: "DWG drawing",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.open.in.reference",
          label: "Known dimension",
        },
      ],
      outputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.open.out.scale",
          label: "Calibrated scale",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.open.out.sheet",
          label: "Clean traced sheet",
        },
      ],
      titleKey: "cases.takeoff_from_dwg.step.open.title",
      titleDefault: "Open the drawing",
      whatKey: "cases.takeoff_from_dwg.step.open.what",
      whatDefault:
        "Bring in the DWG and calibrate the scale against a dimension you trust, such as a gridline spacing or a door width, so a measured line reads in real metres. Switch off the layers you do not need so the sheet is clean to trace over.",
      whyKey: "cases.takeoff_from_dwg.step.open.why",
      whyDefault:
        "A scale that is out by even a few percent multiplies through every area and length you take off, and nobody notices until the concrete order comes back wrong. Calibrating once at the start is a two minute job that protects the whole take-off.",
      moduleLabel: "DWG take-off",
      moduleLabelKey: "onboarding.mod_dwg_takeoff",
      to: "/dwg-takeoff",
    },
    {
      id: "measure",
      icon: "Ruler",
      inputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.measure.in.sheet",
          label: "Calibrated drawing",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.measure.in.scope",
          label: "Items to measure",
        },
      ],
      outputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.measure.out.quantities",
          label: "Measured quantities",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.measure.out.groups",
          label: "Named measurement groups",
        },
      ],
      titleKey: "cases.takeoff_from_dwg.step.measure.title",
      titleDefault: "Measure the work",
      whatKey: "cases.takeoff_from_dwg.step.measure.what",
      whatDefault:
        "Trace polygons for floor areas, run polylines along walls and skirtings, and drop point markers on doors and fittings. Keep each type in its own named group so a wall run, a slab area and a door count stay separate.",
      whyKey: "cases.takeoff_from_dwg.step.measure.why",
      whyDefault:
        "Measurements kept in tidy groups price without untangling and audit in seconds. When a figure looks high, you click the group and see the exact shape that produced it, instead of defending a number you cannot explain.",
      moduleLabel: "Take-off",
      moduleLabelKey: "nav.takeoff_overview",
      to: "/takeoff?tab=measurements",
    },
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.boq.in.quantities",
          label: "Grouped quantities",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.boq.in.rates",
          label: "Unit rates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.takeoff_from_dwg.step.boq.out.boq",
          label: "Priced bill",
        },
        {
          labelKey: "cases.takeoff_from_dwg.step.boq.out.links",
          label: "Live shape links",
        },
      ],
      titleKey: "cases.takeoff_from_dwg.step.boq.title",
      titleDefault: "Price the quantities",
      whatKey: "cases.takeoff_from_dwg.step.boq.what",
      whatDefault:
        "Feed the grouped quantities into the bill and attach a rate to each line. Every position holds a live link back to the shape it was measured from, so a revised drawing flows through to the quantity.",
      whyKey: "cases.takeoff_from_dwg.step.boq.why",
      whyDefault:
        "Typing quantities from a drawing into a separate spreadsheet is where numbers get transposed and areas get dropped. Measuring and pricing in one chain removes that hand-off, and the priced bill can always be traced back to the sheet it came from.",
      moduleLabel: "BOQ",
      moduleLabelKey: "boq.title",
      to: "/projects/:projectId/boq",
    },
  ],
};

export default playbook;
