// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a toolbox talk and record attendance".
//
// Plan a short safety briefing around the day's high-risk activity, deliver it
// to the crew, capture who attended and the topic, then file the record so
// there is provable evidence the briefing happened. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-toolbox-talk-and-record-attendance",
  order: 261,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor"],
  roles: ["hse-officer", "foreman", "site-manager"],
  icon: "HardHat",
  titleKey: "cases.run_a_toolbox_talk_and_record_attendance.title",
  titleDefault: "Run a toolbox talk and record attendance",
  descKey: "cases.run_a_toolbox_talk_and_record_attendance.desc",
  descDefault:
    "Plan a short safety briefing for the day, high-risk activity, deliver it to the crew, capture who attended and the topic, and file the record as provable evidence the briefing happened.",
  estMinutes: 9,
  steps: [
    {
      id: "pick-activity",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.in.plan",
          label: "Daily work plan",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.in.hazards",
          label: "Known site hazards",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.out.activity",
          label: "Selected high-risk activity",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.out.hazard",
          label: "Main hazard identified",
        },
      ],
      titleKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.title",
      titleDefault: "Pick the activity and hazard",
      whatKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.what",
      whatDefault:
        "Look at the work planned for today and pick the highest-risk activity, then note the main hazard the crew will face, working at height, lifting, hot works, live services or whatever leads the day.",
      whyKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.pick-activity.why",
      whyDefault:
        "A toolbox talk only works when it is about the job in front of the crew that morning. Tying it to a real activity and a real hazard is what makes the crew listen instead of nod through it.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "prepare",
      icon: "ClipboardList",
      inputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.in.activity",
          label: "Selected activity",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.in.hazard",
          label: "Identified hazard",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.out.talk",
          label: "Prepared talk points",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.out.controls",
          label: "Controls & PPE list",
        },
      ],
      titleKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.title",
      titleDefault: "Prepare the talk",
      whatKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.what",
      whatDefault:
        "Write a few clear points for the talk, the hazard, the controls in place, the protective equipment needed and what to do if something goes wrong, so you can deliver it in a couple of minutes.",
      whyKey: "cases.run_a_toolbox_talk_and_record_attendance.step.prepare.why",
      whyDefault:
        "A short prepared talk lands better than an off-the-cuff one. Having the controls written down means nothing important gets forgotten in front of the crew.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
    {
      id: "deliver",
      icon: "Users",
      inputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.in.talk",
          label: "Prepared talk",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.in.crew",
          label: "Crew on shift",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.out.attendance",
          label: "Attendance record",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.out.topic",
          label: "Topic & date logged",
        },
      ],
      titleKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.title",
      titleDefault: "Deliver and capture attendance",
      whatKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.what",
      whatDefault:
        "Gather the crew, give the talk, then log who was present against the topic and the date so every name on shift is tied to the briefing they received.",
      whyKey: "cases.run_a_toolbox_talk_and_record_attendance.step.deliver.why",
      whyDefault:
        "Attendance is the proof. If an incident is investigated later, the record of who was briefed on what protects both the worker and the site.",
      moduleLabel: "Field time",
      moduleLabelKey: "nav.field_time",
      to: "/projects/:projectId/field-time",
    },
    {
      id: "file",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.file.in.attendance",
          label: "Attendance record",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.file.in.topic",
          label: "Talk topic",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.file.out.diary",
          label: "Daily diary entry",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.file.out.audit",
          label: "Auditable safety record",
        },
      ],
      titleKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.file.title",
      titleDefault: "File the record in the daily diary",
      whatKey: "cases.run_a_toolbox_talk_and_record_attendance.step.file.what",
      whatDefault:
        "Enter the talk in the daily diary with the topic, the crew present and the time, so it sits alongside the rest of the day, record for the site.",
      whyKey: "cases.run_a_toolbox_talk_and_record_attendance.step.file.why",
      whyDefault:
        "A briefing that lives only in someone, memory did not happen as far as anyone else is concerned. Filing it in the daily record makes it part of the permanent, auditable history of the project.",
      moduleLabel: "Daily diary",
      moduleLabelKey: "nav.daily_diary",
      to: "/projects/:projectId/daily-diary",
    },
    {
      id: "follow-up",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.in.gaps",
          label: "Gaps raised in talk",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.in.diary",
          label: "Diary record",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.out.action",
          label: "Assigned safety action",
        },
        {
          labelKey:
            "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.out.closed",
          label: "Action closed before work",
        },
      ],
      titleKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.title",
      titleDefault: "Follow up any action",
      whatKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.what",
      whatDefault:
        "If the talk raised a missing control, a broken tool or a gap in equipment, raise it as an action with an owner and a date and check it is closed before the activity runs.",
      whyKey:
        "cases.run_a_toolbox_talk_and_record_attendance.step.follow-up.why",
      whyDefault:
        "A talk that surfaces a hazard and then does nothing about it is worse than no talk, because the risk is now known and unmanaged. Following the action through is what actually keeps the crew safe.",
      moduleLabel: "Safety",
      moduleLabelKey: "nav.safety",
      to: "/projects/:projectId/safety",
    },
  ],
};

export default playbook;
