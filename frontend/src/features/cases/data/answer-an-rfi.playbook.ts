// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Answer an RFI".
//
// Turn a site question into a tracked request, chase the answer through the
// right party and file the response so it becomes the record. Content strings
// are key plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "answer-an-rfi",
  order: 100,
  category: "site",
  companyTypes: ["general-contractor", "designer", "project-manager"],
  icon: "MessageSquare",
  titleKey: "cases.answer_an_rfi.title",
  titleDefault: "Answer an RFI",
  descKey: "cases.answer_an_rfi.desc",
  descDefault:
    "Turn a question from the working face into a tracked request, drive it to the party who owns the answer, and file the response so it becomes part of the record.",
  estMinutes: 9,
  steps: [
    {
      id: "raise",
      icon: "HelpCircle",
      inputs: [
        {
          labelKey: "cases.answer_an_rfi.step.raise.in.question",
          label: "Site question",
        },
        {
          labelKey: "cases.answer_an_rfi.step.raise.in.drawing",
          label: "Drawing reference",
        },
      ],
      outputs: [
        {
          labelKey: "cases.answer_an_rfi.step.raise.out.rfi",
          label: "Logged RFI",
        },
        {
          labelKey: "cases.answer_an_rfi.step.raise.out.date",
          label: "Needed-by date",
        },
      ],
      titleKey: "cases.answer_an_rfi.step.raise.title",
      titleDefault: "Raise the request",
      whatKey: "cases.answer_an_rfi.step.raise.what",
      whatDefault:
        "Open the RFI with the actual question, the location and drawing reference it affects, and a needed-by date set from when the crew reaches that work, not an arbitrary week away.",
      whyKey: "cases.answer_an_rfi.step.raise.why",
      whyDefault:
        "A woolly question buys a woolly answer and a week of delay. A tight RFI carrying a real date is also what lets a slow reply be tied back to lost time if it comes to that.",
      moduleLabel: "RFIs",
      moduleLabelKey: "nav.rfi",
      to: "/projects/:projectId/rfi",
    },
    {
      id: "chase",
      icon: "Send",
      inputs: [
        {
          labelKey: "cases.answer_an_rfi.step.chase.in.rfi",
          label: "Open RFI",
        },
        {
          labelKey: "cases.answer_an_rfi.step.chase.in.party",
          label: "Responsible party",
        },
      ],
      outputs: [
        {
          labelKey: "cases.answer_an_rfi.step.chase.out.thread",
          label: "Correspondence thread",
        },
        {
          labelKey: "cases.answer_an_rfi.step.chase.out.answer",
          label: "Response received",
        },
      ],
      titleKey: "cases.answer_an_rfi.step.chase.title",
      titleDefault: "Route and chase it",
      whatKey: "cases.answer_an_rfi.step.chase.what",
      whatDefault:
        "Route it to the designer or consultant who owns the response and keep the correspondence in one thread, with the open item and its due date sitting where everyone can see the clock.",
      whyKey: "cases.answer_an_rfi.step.chase.why",
      whyDefault:
        "RFIs die quietly at the bottom of an inbox. Keeping the routing, the reminders and the reply in a single visible trail is what keeps the answer moving and the history defensible.",
      moduleLabel: "Correspondence",
      moduleLabelKey: "nav.correspondence",
      to: "/projects/:projectId/correspondence",
    },
    {
      id: "file",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey: "cases.answer_an_rfi.step.file.in.answer",
          label: "RFI response",
        },
        {
          labelKey: "cases.answer_an_rfi.step.file.in.revised",
          label: "Revised drawing",
        },
      ],
      outputs: [
        {
          labelKey: "cases.answer_an_rfi.step.file.out.filed",
          label: "Filed answer",
        },
        {
          labelKey: "cases.answer_an_rfi.step.file.out.closed",
          label: "Closed RFI",
        },
      ],
      titleKey: "cases.answer_an_rfi.step.file.title",
      titleDefault: "File the answer",
      whatKey: "cases.answer_an_rfi.step.file.what",
      whatDefault:
        "Attach the answer and any superseded or revised drawing to the project files, link it back to the affected work, and close the RFI so the loop is shut.",
      whyKey: "cases.answer_an_rfi.step.file.why",
      whyDefault:
        "An answer buried in a single inbox helps nobody at the trowel. A filed, closed RFI is what stops the same question being asked again next month by the next trade.",
      moduleLabel: "Files",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
  ],
};

export default playbook;
