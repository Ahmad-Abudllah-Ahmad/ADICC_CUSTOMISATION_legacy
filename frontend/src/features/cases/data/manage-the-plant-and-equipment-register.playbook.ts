// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Manage the plant and equipment register".
//
// Keep a live plant register: record owned and hired machines, book their hours
// to the job, flag inspections and service, and report utilization so hire and
// off-hire calls are made on data, not guesswork.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "manage-the-plant-and-equipment-register",
  order: 310,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor"],
  icon: "Boxes",
  titleKey: "cases.manage_the_plant_and_equipment_register.title",
  titleDefault: "Manage the plant and equipment register",
  descKey: "cases.manage_the_plant_and_equipment_register.desc",
  descDefault:
    "Register owned and hired plant, book its hours to the job, keep it inspected, and report utilization to time hire calls.",
  estMinutes: 8,
  steps: [
    {
      id: "register",
      icon: "Database",
      inputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.register.in.owned",
          label: "Owned machines",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.register.in.hired",
          label: "Hire contracts",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.register.out.register",
          label: "Plant register",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.register.out.rates",
          label: "Rates & meter readings",
        },
      ],
      titleKey:
        "cases.manage_the_plant_and_equipment_register.step.register.title",
      titleDefault: "Register owned and hired plant",
      whatKey:
        "cases.manage_the_plant_and_equipment_register.step.register.what",
      whatDefault:
        "List every owned and hired machine with its rate, current hour-meter reading and service interval.",
      whyKey: "cases.manage_the_plant_and_equipment_register.step.register.why",
      whyDefault:
        "Plant that is not on a register gets hired twice or serviced late. One list is the base for both cost and maintenance.",
      moduleLabel: "Equipment",
      to: "/equipment",
    },
    {
      id: "book-hours",
      icon: "Clock",
      inputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.book-hours.in.register",
          label: "Plant register",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.book-hours.in.timesheet",
          label: "Field time sheet",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.book-hours.out.hours",
          label: "Booked plant hours",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.book-hours.out.cost",
          label: "Plant cost to job",
        },
      ],
      titleKey:
        "cases.manage_the_plant_and_equipment_register.step.book-hours.title",
      titleDefault: "Book plant hours to the job",
      whatKey:
        "cases.manage_the_plant_and_equipment_register.step.book-hours.what",
      whatDefault:
        "On the field time sheet, book machine hours to the job next to the labour hours for the same crew.",
      whyKey:
        "cases.manage_the_plant_and_equipment_register.step.book-hours.why",
      whyDefault:
        "Plant that is not booked to a job never lands on the cost report. Capturing it with labour gives the true cost of the work done.",
      moduleLabel: "Field Time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "maintenance",
      icon: "ShieldAlert",
      inputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.maintenance.in.hours",
          label: "Machine hours & dates",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.maintenance.in.intervals",
          label: "Service intervals",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.maintenance.out.flags",
          label: "Service-due flags",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.maintenance.out.alerts",
          label: "Inspection alerts",
        },
      ],
      titleKey:
        "cases.manage_the_plant_and_equipment_register.step.maintenance.title",
      titleDefault: "Flag inspections and service",
      whatKey:
        "cases.manage_the_plant_and_equipment_register.step.maintenance.what",
      whatDefault:
        "Flag machines coming due for statutory inspection or service against their hours and dates.",
      whyKey:
        "cases.manage_the_plant_and_equipment_register.step.maintenance.why",
      whyDefault:
        "An uninspected lift or a machine past service is a stop-work and a safety risk. Flagging early keeps plant legal and running.",
      moduleLabel: "Equipment",
      to: "/projects/:projectId/equipment",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.report.in.hours",
          label: "Booked plant hours",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.report.in.fleet",
          label: "Fleet register",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.report.out.report",
          label: "Utilization report",
        },
        {
          labelKey:
            "cases.manage_the_plant_and_equipment_register.step.report.out.offhire",
          label: "Off-hire list",
        },
      ],
      titleKey:
        "cases.manage_the_plant_and_equipment_register.step.report.title",
      titleDefault: "Report utilization and idle plant",
      whatKey: "cases.manage_the_plant_and_equipment_register.step.report.what",
      whatDefault:
        "Report utilization and idle time across the fleet so you can see what is earning and what is sitting.",
      whyKey: "cases.manage_the_plant_and_equipment_register.step.report.why",
      whyDefault:
        "Idle hired plant burns money every day. Utilization figures tell you what to off-hire and what to move, instead of guessing.",
      moduleLabel: "Reports",
      to: "/reports",
    },
  ],
};

export default playbook;
