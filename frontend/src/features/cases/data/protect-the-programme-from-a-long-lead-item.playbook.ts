// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Protect the programme from a long-lead item".
//
// Stop a long-lead item stalling the job: find the items whose delivery beats the
// programme, tie their order dates to the schedule, and report the exposure left.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "protect-the-programme-from-a-long-lead-item",
  order: 294,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager"],
  icon: "CalendarClock",
  titleKey: "cases.protect_the_programme_from_a_long_lead_item.title",
  titleDefault: "Protect the programme from a long-lead item",
  descKey: "cases.protect_the_programme_from_a_long_lead_item.desc",
  descDefault:
    "Stop a long-lead item stalling the job: find the items whose delivery beats the programme, tie their order dates to the schedule, and report the exposure that is left.",
  longDescKey: "cases.protect_the_programme_from_a_long_lead_item.longdesc",
  longDescDefault:
    "A single long-lead item ordered too late can hold up a whole trade and blow the programme no matter how well everything else runs. This case finds the items whose manufacture and delivery time threatens the dates that need them, pins their order-by dates to the schedule so procurement moves in time, and reports the exposure that remains so the risk is managed rather than discovered on site.",
  estMinutes: 9,
  steps: [
    {
      id: "identify",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.identify.in.schedule",
          label: "Procurement schedule",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.identify.in.leadtimes",
          label: "Supplier lead times",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.identify.out.items",
          label: "Long-lead item list",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.identify.out.dates",
          label: "Required-on-site dates",
        },
      ],
      titleKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.identify.title",
      titleDefault: "Find the long-lead items",
      whatKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.identify.what",
      whatDefault:
        "Go through the procurement schedule for the items whose lead time is long against the programme, from switchgear to bespoke facades, and note the date each is actually needed on site.",
      whyKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.identify.why",
      whyDefault:
        "A long-lead item nobody flagged is the one that stops a trade dead. Finding them early is what gives you the weeks you need to order in time instead of expediting at a premium later.",
      moduleLabel: "Procurement",
      moduleLabelKey: "procurement.title",
      to: "/projects/:projectId/procurement",
    },
    {
      id: "schedule",
      icon: "CalendarClock",
      inputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.schedule.in.items",
          label: "Long-lead item list",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.schedule.in.programme",
          label: "Baseline programme",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.schedule.out.orderby",
          label: "Order-by dates",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.schedule.out.milestones",
          label: "Procurement milestones",
        },
      ],
      titleKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.schedule.title",
      titleDefault: "Tie order dates to the programme",
      whatKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.schedule.what",
      whatDefault:
        "Work back from each required-on-site date through the lead time to the date the order must be placed, and set those order-by dates as milestones on the programme the team works to.",
      whyKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.schedule.why",
      whyDefault:
        "A required-on-site date on its own does not tell procurement when to buy. Backing the lead time onto the programme is what turns a delivery need into an order-by milestone somebody is accountable for.",
      moduleLabel: "Advanced schedule",
      moduleLabelKey: "nav.schedule_advanced",
      to: "/schedule-advanced",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.report.in.orderby",
          label: "Order-by dates",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.report.in.status",
          label: "Current procurement status",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.report.out.exposure",
          label: "Exposure report",
        },
        {
          labelKey:
            "cases.protect_the_programme_from_a_long_lead_item.step.report.out.atrisk",
          label: "At-risk items",
        },
      ],
      titleKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.report.title",
      titleDefault: "Report the remaining exposure",
      whatKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.report.what",
      whatDefault:
        "Report which long-lead items are ordered against plan and which order-by dates are slipping, so the items still at risk to the programme are visible to the team at every review.",
      whyKey:
        "cases.protect_the_programme_from_a_long_lead_item.step.report.why",
      whyDefault:
        "A procurement risk you cannot see is one you manage by luck. Reporting the exposure keeps the slipping items in front of the people who can expedite them before they become a delay on site.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
