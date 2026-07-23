// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Capture daywork and time and materials".
//
// Turn instructed extra work into a paid claim: record the hours, plant and
// materials as they happen, get the sheet signed on the day, then submit it
// against the contract. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "capture-daywork-and-time-and-materials",
  order: 150,
  category: "site",
  companyTypes: ["subcontractor", "general-contractor", "cost-consultant"],
  icon: "Clock",
  titleKey: "cases.capture_daywork_and_time_and_materials.title",
  titleDefault: "Capture daywork and time and materials",
  descKey: "cases.capture_daywork_and_time_and_materials.desc",
  descDefault:
    "Turn instructed extra work into a claim that gets paid: record the labour, plant and materials as it happens, get the sheet signed the same day, then submit it against the contract.",
  estMinutes: 9,
  steps: [
    {
      id: "record",
      icon: "Clock",
      inputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.record.in.instruction",
          label: "Site instruction",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.record.in.resources",
          label: "Labour, plant and materials",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.record.out.record",
          label: "Daywork record",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.record.out.coded",
          label: "Cost-coded entries",
        },
      ],
      titleKey:
        "cases.capture_daywork_and_time_and_materials.step.record.title",
      titleDefault: "Record the hours and materials",
      whatKey: "cases.capture_daywork_and_time_and_materials.step.record.what",
      whatDefault:
        "As the instructed work runs, book the labour hours by gang, the plant on it and the materials used, tagged to the instruction that authorised it and to the right cost code.",
      whyKey: "cases.capture_daywork_and_time_and_materials.step.record.why",
      whyDefault:
        "Daywork paid on records reconstructed at month end always comes up short, because nobody remembers the exact hours. Captured live, against the instruction, it is a claim built on fact rather than memory.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "sign",
      icon: "NotebookPen",
      inputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.sign.in.record",
          label: "Daywork record",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.sign.in.photo",
          label: "Photo of the work",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.sign.out.signed",
          label: "Signed daywork sheet",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.sign.out.diary",
          label: "Diary entry",
        },
      ],
      titleKey: "cases.capture_daywork_and_time_and_materials.step.sign.title",
      titleDefault: "Get the sheet signed on the day",
      whatKey: "cases.capture_daywork_and_time_and_materials.step.sign.what",
      whatDefault:
        "Log the daywork in the diary with a photo of the work, and get the client representative or their agent to sign the sheet agreeing the resources while they are still standing in front of them.",
      whyKey: "cases.capture_daywork_and_time_and_materials.step.sign.why",
      whyDefault:
        "A signature agreeing the hours on the day settles the argument before it starts. An unsigned sheet argued weeks later gets whittled down, and the difference comes straight off your margin.",
      moduleLabel: "Daily Diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "submit",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.submit.in.signed",
          label: "Signed daywork sheet",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.submit.in.rates",
          label: "Contract daywork rates",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.submit.out.claim",
          label: "Priced daywork claim",
        },
        {
          labelKey:
            "cases.capture_daywork_and_time_and_materials.step.submit.out.valuation",
          label: "Payment valuation",
        },
      ],
      titleKey:
        "cases.capture_daywork_and_time_and_materials.step.submit.title",
      titleDefault: "Submit it against the contract",
      whatKey: "cases.capture_daywork_and_time_and_materials.step.submit.what",
      whatDefault:
        "Price the agreed resources at the contract daywork rates or percentages, attach the signed sheets and the instruction, and submit the valuation so it flows into the next payment.",
      whyKey: "cases.capture_daywork_and_time_and_materials.step.submit.why",
      whyDefault:
        "Daywork that is never priced and submitted is work you did for free. Turning the signed record into a valuation against the contract is the step that actually converts the effort into money.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
  ],
};

export default playbook;
