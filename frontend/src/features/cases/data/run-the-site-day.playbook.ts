// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run the site day".
//
// The daily site loop: log the diary, book the labour and plant hours, capture
// photos and raise a safety observation, so a day on site becomes a record you
// can stand behind. Content strings are key plus inline English default.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-the-site-day",
  order: 50,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  icon: "HardHat",
  titleKey: "cases.run_the_site_day.title",
  titleDefault: "Run the site day",
  descKey: "cases.run_the_site_day.desc",
  descDefault:
    "Close the day out properly: record the diary, book the labour and plant hours, upload the photos and log a safety observation, so the day survives as evidence you can lean on.",
  estMinutes: 9,
  steps: [
    {
      id: "diary",
      icon: "NotebookPen",
      inputs: [
        {
          labelKey: "cases.run_the_site_day.step.diary.in.weather",
          label: "Weather & conditions",
        },
        {
          labelKey: "cases.run_the_site_day.step.diary.in.crews",
          label: "Gangs & visitors",
        },
        {
          labelKey: "cases.run_the_site_day.step.diary.in.progress",
          label: "Work achieved & hold-ups",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_site_day.step.diary.out.entry",
          label: "Dated diary entry",
        },
        {
          labelKey: "cases.run_the_site_day.step.diary.out.record",
          label: "Contemporaneous record",
        },
      ],
      titleKey: "cases.run_the_site_day.step.diary.title",
      titleDefault: "Write the site diary",
      whatKey: "cases.run_the_site_day.step.diary.what",
      whatDefault:
        "Note the weather, the gangs and visitors on site, the work each area achieved and any hold-up such as a late delivery or a service strike. Written the same day, this is your contemporaneous record.",
      whyKey: "cases.run_the_site_day.step.diary.why",
      whyDefault:
        "A diary entry made on the day carries evidential weight that a reconstruction written months later never will. When a delay claim or a dispute lands, this is the first record the commercial team reaches for.",
      moduleLabel: "Site diary",
      moduleLabelKey: "onboarding.mod_daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "hours",
      icon: "Clock",
      inputs: [
        {
          labelKey: "cases.run_the_site_day.step.hours.in.crews",
          label: "Gangs on site",
        },
        {
          labelKey: "cases.run_the_site_day.step.hours.in.plant",
          label: "Plant on hire",
        },
        {
          labelKey: "cases.run_the_site_day.step.hours.in.codes",
          label: "Cost codes",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_site_day.step.hours.out.hours",
          label: "Booked labour & plant hours",
        },
        {
          labelKey: "cases.run_the_site_day.step.hours.out.cost",
          label: "Cost-coded spend",
        },
      ],
      titleKey: "cases.run_the_site_day.step.hours.title",
      titleDefault: "Book labour and plant hours",
      whatKey: "cases.run_the_site_day.step.hours.what",
      whatDefault:
        "Book the hours each gang and every item of plant put in against this project, tagged to the right cost code so the spend lands where the budget expects it.",
      whyKey: "cases.run_the_site_day.step.hours.why",
      whyDefault:
        "Hours captured while the shift is fresh are hours you can bill, cost against the budget and check against output. Reconstructed at month end they turn into guesswork, and guesswork on labour is where margin quietly disappears.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "photos",
      icon: "Camera",
      inputs: [
        {
          labelKey: "cases.run_the_site_day.step.photos.in.shots",
          label: "Photos taken on site",
        },
        {
          labelKey: "cases.run_the_site_day.step.photos.in.entry",
          label: "Diary entry",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_site_day.step.photos.out.gallery",
          label: "Tagged site gallery",
        },
        {
          labelKey: "cases.run_the_site_day.step.photos.out.dated",
          label: "Dated progress photos",
        },
      ],
      titleKey: "cases.run_the_site_day.step.photos.title",
      titleDefault: "Capture site photos",
      whatKey: "cases.run_the_site_day.step.photos.what",
      whatDefault:
        "Add the day photos from the project files. They are tagged as site pictures and show up in the gallery, the day strip and the diary entry, dated and in sequence.",
      whyKey: "cases.run_the_site_day.step.photos.why",
      whyDefault:
        "A dated photo ends an argument that words drag out. It proves progress, records the condition you inherited and captures reinforcement or services before the pour or the plasterboard hides them for good.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "safety",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey: "cases.run_the_site_day.step.safety.in.hazard",
          label: "Hazard or near miss",
        },
        {
          labelKey: "cases.run_the_site_day.step.safety.in.talk",
          label: "Toolbox talk",
        },
      ],
      outputs: [
        {
          labelKey: "cases.run_the_site_day.step.safety.out.observation",
          label: "Logged observation",
        },
        {
          labelKey: "cases.run_the_site_day.step.safety.out.trend",
          label: "Safety trend data",
        },
      ],
      titleKey: "cases.run_the_site_day.step.safety.title",
      titleDefault: "Log a safety observation",
      whatKey: "cases.run_the_site_day.step.safety.what",
      whatDefault:
        "Log any hazard spotted, near miss reported or good practice worth repeating, and name who owns the close-out. Record the toolbox talk and who attended it here as well.",
      whyKey: "cases.run_the_site_day.step.safety.why",
      whyDefault:
        "What gets recorded gets acted on, and the trend across many small entries is what warns you before a serious event. A near miss written up today is often the injury you avoid next week.",
      moduleLabel: "Safety",
      moduleLabelKey: "safety.title",
      to: "/projects/:projectId/safety",
    },
  ],
};

export default playbook;
