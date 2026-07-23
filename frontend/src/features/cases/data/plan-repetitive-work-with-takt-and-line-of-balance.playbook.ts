// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Plan repetitive work with takt and line of balance".
//
// Plan repeating works as a takt plan: zone the building, set the takt time,
// level the crews so each trade holds the beat, and publish the line of balance
// to the trades who have to deliver it.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "plan-repetitive-work-with-takt-and-line-of-balance",
  order: 306,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "subcontractor"],
  icon: "LineChart",
  titleKey: "cases.plan_repetitive_work_with_takt_and_line_of_balance.title",
  titleDefault: "Plan repetitive work with takt and line of balance",
  descKey: "cases.plan_repetitive_work_with_takt_and_line_of_balance.desc",
  descDefault:
    "Zone the works, set a takt beat, level the crews to hold it, and publish the line of balance to the trades.",
  estMinutes: 9,
  steps: [
    {
      id: "zones",
      icon: "Layers",
      inputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.in.layout",
          label: "Floor plans",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.in.scope",
          label: "Scope of works",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.out.zones",
          label: "Even work zones",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.out.activities",
          label: "Repeating activities",
        },
      ],
      titleKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.title",
      titleDefault: "Zone the repeating works",
      whatKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.what",
      whatDefault:
        "Split the building into zones or floors and define the activities that repeat in each one.",
      whyKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.zones.why",
      whyDefault:
        "Repetitive work only flows when the zones are even and the sequence is the same everywhere. This is the groundwork for a takt plan.",
      moduleLabel: "Schedule",
      to: "/schedule",
    },
    {
      id: "takt-time",
      icon: "Clock",
      inputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.in.zones",
          label: "Even work zones",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.in.durations",
          label: "Activity durations",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.out.takt",
          label: "Takt time",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.out.train",
          label: "Trade-train sequence",
        },
      ],
      titleKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.title",
      titleDefault: "Set the takt and trade-train",
      whatKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.what",
      whatDefault:
        "Set one takt time for the zone and watch each trade move zone to zone as a train across the plan.",
      whyKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.takt-time.why",
      whyDefault:
        "A steady takt beat stops trades tripping over each other, and it makes a slip obvious the day it happens, not a month later.",
      moduleLabel: "Takt",
      to: "/takt",
    },
    {
      id: "level-crews",
      icon: "Users",
      inputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.in.takt",
          label: "Takt time",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.in.crews",
          label: "Trade crews",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.out.levelled",
          label: "Levelled crews",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.out.histogram",
          label: "Smoothed labour peaks",
        },
      ],
      titleKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.title",
      titleDefault: "Level the crews to the beat",
      whatKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.what",
      whatDefault:
        "Size and level the crews so every trade can finish its zone inside the takt time, with no peak it cannot man.",
      whyKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.level-crews.why",
      whyDefault:
        "If one crew cannot hold the beat, the whole train stalls behind it. Levelling early is cheaper than chasing labour on site.",
      moduleLabel: "Resources",
      to: "/projects/:projectId/resources",
    },
    {
      id: "publish",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.in.plan",
          label: "Levelled takt plan",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.in.trades",
          label: "Trade contacts",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.out.lob",
          label: "Published line of balance",
        },
        {
          labelKey:
            "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.out.dates",
          label: "Per-trade zone dates",
        },
      ],
      titleKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.title",
      titleDefault: "Publish the plan to the trades",
      whatKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.what",
      whatDefault:
        "Publish the takt plan and hand each trade its zones and dates.",
      whyKey:
        "cases.plan_repetitive_work_with_takt_and_line_of_balance.step.publish.why",
      whyDefault:
        "A takt plan only works when every foreman knows their beat. Publishing it sets the shared rhythm the whole job runs to.",
      moduleLabel: "Reports",
      to: "/reports",
    },
  ],
};

export default playbook;
