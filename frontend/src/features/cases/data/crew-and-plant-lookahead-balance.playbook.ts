// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Balance crews and plant across the programme".
//
// A project manager case: read the labour and plant the near-term programme
// actually needs, check it against what is booked on site, and close the gap
// before a task stalls for want of a hand or a machine. Content strings are
// key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "crew-and-plant-lookahead-balance",
  order: 225,
  category: "planning",
  companyTypes: ["project-manager", "general-contractor", "subcontractor"],
  icon: "HardHat",
  titleKey: "cases.crew_and_plant_lookahead_balance.title",
  titleDefault: "Balance crews and plant across the programme",
  descKey: "cases.crew_and_plant_lookahead_balance.desc",
  descDefault:
    "Read the labour and plant the near-term programme actually needs, check it against what is booked on site, and close the gap before a task stalls for want of a hand or a machine.",
  estMinutes: 10,
  steps: [
    {
      id: "read",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.read.in.programme",
          label: "Project programme",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.read.in.window",
          label: "Lookahead window",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.read.out.demand",
          label: "Crew and plant demand",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.read.out.needs",
          label: "Trade-by-trade needs",
        },
      ],
      titleKey: "cases.crew_and_plant_lookahead_balance.step.read.title",
      titleDefault: "Read the near-term demand",
      whatKey: "cases.crew_and_plant_lookahead_balance.step.read.what",
      whatDefault:
        "Look at the next few weeks of activities on the programme and note the trade, crew size and any plant each one needs to run to plan.",
      whyKey: "cases.crew_and_plant_lookahead_balance.step.read.why",
      whyDefault:
        "A task with no crew or crane booked against it is a task that will not start on the day the programme says it will.",
      moduleLabel: "Advanced scheduling",
      moduleLabelKey: "onboarding.mod_schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "check",
      icon: "Clock",
      inputs: [
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.check.in.demand",
          label: "Crew and plant demand",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.check.in.booked",
          label: "Booked field hours",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.check.in.plant",
          label: "Plant bookings",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.check.out.gaps",
          label: "Resource shortfall list",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.check.out.flags",
          label: "Flagged short trades",
        },
      ],
      titleKey: "cases.crew_and_plant_lookahead_balance.step.check.title",
      titleDefault: "Check what is actually booked",
      whatKey: "cases.crew_and_plant_lookahead_balance.step.check.what",
      whatDefault:
        "Compare the hours and plant booked in the field against what the lookahead calls for, and flag the trades running short before the week begins.",
      whyKey: "cases.crew_and_plant_lookahead_balance.step.check.why",
      whyDefault:
        "Booked hours are the ground truth of what will really turn up on site. Catching a shortfall a week out is a phone call; catching it on the day is a stalled gang.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "close",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey: "cases.crew_and_plant_lookahead_balance.step.close.in.gaps",
          label: "Resource shortfall list",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.close.in.available",
          label: "Available crews and plant",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.close.out.lookahead",
          label: "Resourced lookahead",
        },
        {
          labelKey:
            "cases.crew_and_plant_lookahead_balance.step.close.out.report",
          label: "Resourcing report",
        },
      ],
      titleKey: "cases.crew_and_plant_lookahead_balance.step.close.title",
      titleDefault: "Close the gap and report it",
      whatKey: "cases.crew_and_plant_lookahead_balance.step.close.what",
      whatDefault:
        "Arrange the extra crew, plant or overtime needed to cover the gap, and report the resourced lookahead so the wider team can see the plan is properly resourced, not just dated.",
      whyKey: "cases.crew_and_plant_lookahead_balance.step.close.why",
      whyDefault:
        "A lookahead with dates but no resourcing behind it is a wish list. Showing it is resourced is what makes the plan believable to the trades who have to deliver it.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
