// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a 5D cost-loaded model".
//
// Start from the priced bill, link each cost block to its model elements and
// programme dates, and tie the blocks to schedule activities so the cash
// curve follows the plan. Content strings are key plus inline English default
// and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "build-a-5d-cost-loaded-model",
  order: 334,
  category: "estimating",
  companyTypes: ["cost-consultant", "general-contractor"],
  icon: "LineChart",
  titleKey: "cases.build_a_5d_cost_loaded_model.title",
  titleDefault: "Build a 5D cost-loaded model",
  descKey: "cases.build_a_5d_cost_loaded_model.desc",
  descDefault:
    "Start from the priced bill, link cost to the model and the programme, and tie the cost blocks to schedule activities so you can see cost over time and the cash curve follows the plan.",
  estMinutes: 10,
  steps: [
    {
      id: "boq",
      icon: "Table2",
      inputs: [
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.boq.in.boq",
          label: "Priced BOQ",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.boq.in.rates",
          label: "Unit rates",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.boq.in.quantities",
          label: "Line quantities",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.boq.out.verified",
          label: "Verified priced bill",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.boq.out.blocks",
          label: "Cost blocks",
        },
      ],
      titleKey: "cases.build_a_5d_cost_loaded_model.step.boq.title",
      titleDefault: "Start from the priced bill",
      whatKey: "cases.build_a_5d_cost_loaded_model.step.boq.what",
      whatDefault:
        "Open the priced BOQ and confirm every line carries a rate and a quantity, since the 5D model is only ever as good as the bill you load onto it.",
      whyKey: "cases.build_a_5d_cost_loaded_model.step.boq.why",
      whyDefault:
        "Cost-loading a model built on gaps just spreads those gaps across the programme. A complete priced bill is the foundation the whole cash curve stands on.",
      moduleLabel: "BOQ",
      to: "/boq",
    },
    {
      id: "link",
      icon: "Combine",
      inputs: [
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.link.in.blocks",
          label: "Cost blocks",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.link.in.model",
          label: "Model elements",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.link.in.dates",
          label: "Programme dates",
        },
      ],
      outputs: [
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.link.out.linked",
          label: "Cost-loaded model",
        },
        {
          labelKey: "cases.build_a_5d_cost_loaded_model.step.link.out.orphans",
          label: "Unlinked packages flagged",
        },
      ],
      titleKey: "cases.build_a_5d_cost_loaded_model.step.link.title",
      titleDefault: "Link cost to model and time",
      whatKey: "cases.build_a_5d_cost_loaded_model.step.link.what",
      whatDefault:
        "Map each BOQ package onto its model elements and its programme dates, so every cost block knows where it is built and when it is spent.",
      whyKey: "cases.build_a_5d_cost_loaded_model.step.link.why",
      whyDefault:
        "Cost tied to geometry and time turns a flat total into a picture of where the money is and when it leaves. It is also how you catch a package that is priced but has no home in the model.",
      moduleLabel: "5D Cost Model",
      to: "/5d",
    },
    {
      id: "schedule",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.build_a_5d_cost_loaded_model.step.schedule.in.blocks",
          label: "Cost-loaded blocks",
        },
        {
          labelKey:
            "cases.build_a_5d_cost_loaded_model.step.schedule.in.activities",
          label: "Schedule activities",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.build_a_5d_cost_loaded_model.step.schedule.out.curve",
          label: "Cash flow curve",
        },
        {
          labelKey:
            "cases.build_a_5d_cost_loaded_model.step.schedule.out.forecast",
          label: "Time-phased spend",
        },
      ],
      titleKey: "cases.build_a_5d_cost_loaded_model.step.schedule.title",
      titleDefault: "Tie cost to the programme",
      whatKey: "cases.build_a_5d_cost_loaded_model.step.schedule.what",
      whatDefault:
        "Attach each cost block to the schedule activity that delivers it, so the spend spreads across the real start and finish dates instead of a flat monthly average.",
      whyKey: "cases.build_a_5d_cost_loaded_model.step.schedule.why",
      whyDefault:
        "A cash curve driven by the actual programme tells the client and the bank when the money is really needed. When the programme slips, the forecast spend moves with it instead of lying to everyone.",
      moduleLabel: "Schedule",
      to: "/schedule",
    },
  ],
};

export default playbook;
