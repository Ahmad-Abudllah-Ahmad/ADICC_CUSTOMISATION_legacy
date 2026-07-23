// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a progress meeting and drive the actions".
//
// Chair a site progress meeting inside the platform: record the minutes and
// decisions, turn each one into an owned task or a formal RFI, then issue the
// minutes and the open actions to everyone who attended.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-a-progress-meeting-and-drive-the-actions",
  order: 302,
  category: "planning",
  companyTypes: ["general-contractor", "project-manager", "subcontractor"],
  icon: "Users",
  titleKey: "cases.run_a_progress_meeting_and_drive_the_actions.title",
  titleDefault: "Run a progress meeting and drive the actions",
  descKey: "cases.run_a_progress_meeting_and_drive_the_actions.desc",
  descDefault:
    "Chair a site progress meeting, capture the decisions, turn each into an owned action or RFI, then issue the minutes.",
  estMinutes: 8,
  steps: [
    {
      id: "agenda-minutes",
      icon: "MessageSquare",
      inputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.in.agenda",
          label: "Meeting agenda",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.in.attendees",
          label: "Attendees",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.out.minutes",
          label: "Logged minutes",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.out.decisions",
          label: "Recorded decisions",
        },
      ],
      titleKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.title",
      titleDefault: "Chair the meeting and log the minutes",
      whatKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.what",
      whatDefault:
        "Open the meeting, work the agenda, and record attendance, minutes and every decision as they are made.",
      whyKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.agenda-minutes.why",
      whyDefault:
        "A meeting with no written record gets re-argued next week, and a verbal decision does not hold up in a dispute.",
      moduleLabel: "Meetings",
      to: "/projects/:projectId/meetings",
    },
    {
      id: "actions",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.in.decisions",
          label: "Recorded decisions",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.in.owners",
          label: "Named owners",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.out.tasks",
          label: "Owned tasks",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.out.duedates",
          label: "Due dates set",
        },
      ],
      titleKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.title",
      titleDefault: "Turn decisions into owned actions",
      whatKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.what",
      whatDefault:
        "Raise a task for each action coming out of the meeting, each with a named owner and a due date.",
      whyKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.actions.why",
      whyDefault:
        "An action with no owner and no date never gets done. Naming both is what makes progress trackable and someone accountable.",
      moduleLabel: "Tasks",
      to: "/projects/:projectId/tasks",
    },
    {
      id: "rfi",
      icon: "HelpCircle",
      inputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.in.questions",
          label: "Unresolved questions",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.in.minutes",
          label: "Meeting minutes",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.out.rfi",
          label: "Formal RFIs",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.out.log",
          label: "Dated RFI log",
        },
      ],
      titleKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.title",
      titleDefault: "Raise RFIs for open questions",
      whatKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.what",
      whatDefault:
        "For every unresolved technical question, raise a formal RFI to the designer so the answer is logged and dated.",
      whyKey: "cases.run_a_progress_meeting_and_drive_the_actions.step.rfi.why",
      whyDefault:
        "A question left in the notes stalls the works and gets forgotten. A formal RFI forces a dated answer on the record.",
      moduleLabel: "RFI",
      to: "/projects/:projectId/rfi",
    },
    {
      id: "issue-minutes",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.in.minutes",
          label: "Logged minutes",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.in.actions",
          label: "Open actions",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.out.issued",
          label: "Issued minutes",
        },
        {
          labelKey:
            "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.out.circulated",
          label: "Circulated actions",
        },
      ],
      titleKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.title",
      titleDefault: "Issue the minutes and actions",
      whatKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.what",
      whatDefault:
        "Generate the minutes and the open-actions list and send them to everyone who attended.",
      whyKey:
        "cases.run_a_progress_meeting_and_drive_the_actions.step.issue-minutes.why",
      whyDefault:
        "Minutes only bind people once they are issued. Circulating the actions closes the loop and starts the clock on every due date.",
      moduleLabel: "Reports",
      to: "/reports",
    },
  ],
};

export default playbook;
