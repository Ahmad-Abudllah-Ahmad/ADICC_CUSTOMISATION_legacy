// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Agree the final account and release retention".
//
// Close the contract cleanly: settle the final account from the agreed
// variations and valuations, release the retention due, and report the outturn.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "agree-the-final-account-and-release-retention",
  order: 284,
  category: "commercial",
  companyTypes: ["general-contractor", "cost-consultant", "subcontractor"],
  stage: "handover",
  icon: "Handshake",
  titleKey: "cases.agree_the_final_account_and_release_retention.title",
  titleDefault: "Agree the final account and release retention",
  descKey: "cases.agree_the_final_account_and_release_retention.desc",
  descDefault:
    "Close the contract cleanly: settle the final account from the agreed variations and valuations, release the retention that is due, and report the outturn against budget.",
  longDescKey: "cases.agree_the_final_account_and_release_retention.longdesc",
  longDescDefault:
    "A contract that drags on unsettled ties up retention and sours the relationship long after the work is done. This case builds the final account from the variations and valuations already agreed, releases the retention that has genuinely fallen due, and reports the outturn so both sides close the job knowing exactly what it landed at against the budget.",
  estMinutes: 9,
  steps: [
    {
      id: "account",
      icon: "FileSignature",
      inputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.account.in.variations",
          label: "Agreed variations",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.account.in.valuations",
          label: "Certified valuations",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.account.out.total",
          label: "Final account total",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.account.out.open",
          label: "Outstanding items",
        },
      ],
      titleKey:
        "cases.agree_the_final_account_and_release_retention.step.account.title",
      titleDefault: "Build the final account",
      whatKey:
        "cases.agree_the_final_account_and_release_retention.step.account.what",
      whatDefault:
        "Pull the agreed variations and the certified valuations into one final account, settle the last few open items, and confirm the total both sides are signing up to.",
      whyKey:
        "cases.agree_the_final_account_and_release_retention.step.account.why",
      whyDefault:
        "A final account assembled from loose emails is one nobody trusts to sign. Building it from the variations and valuations already agreed is what turns a negotiation into a number everyone can accept.",
      moduleLabel: "Contracts",
      moduleLabelKey: "nav.contracts",
      to: "/projects/:projectId/contracts",
    },
    {
      id: "settle",
      icon: "Banknote",
      inputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.settle.in.total",
          label: "Final account total",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.settle.in.retention",
          label: "Retention held",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.settle.out.release",
          label: "Retention release",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.settle.out.final",
          label: "Final payment",
        },
      ],
      titleKey:
        "cases.agree_the_final_account_and_release_retention.step.settle.title",
      titleDefault: "Release the retention due",
      whatKey:
        "cases.agree_the_final_account_and_release_retention.step.settle.what",
      whatDefault:
        "Against the agreed account, release the retention that has fallen due now the defects are cleared, and set the final payment, keeping back only what a live defect still justifies.",
      whyKey:
        "cases.agree_the_final_account_and_release_retention.step.settle.why",
      whyDefault:
        "Retention sat on past its release date is the subcontractor's money you are holding for no reason, and it poisons the next tender. Releasing it on time is fair, and it is what gets you a keen price next round.",
      moduleLabel: "Finance",
      moduleLabelKey: "nav.finance",
      to: "/projects/:projectId/finance",
    },
    {
      id: "report",
      icon: "FileBarChart",
      inputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.report.in.total",
          label: "Final account total",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.report.in.budget",
          label: "Original budget",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.report.out.outturn",
          label: "Outturn report",
        },
        {
          labelKey:
            "cases.agree_the_final_account_and_release_retention.step.report.out.variance",
          label: "Variance breakdown",
        },
      ],
      titleKey:
        "cases.agree_the_final_account_and_release_retention.step.report.title",
      titleDefault: "Report the outturn against budget",
      whatKey:
        "cases.agree_the_final_account_and_release_retention.step.report.what",
      whatDefault:
        "Run the report that sets the settled final account against the budget you started with, break down where the money moved, and file it as the closing position on the job.",
      whyKey:
        "cases.agree_the_final_account_and_release_retention.step.report.why",
      whyDefault:
        "A job closed with no outturn report teaches you nothing for the next one. Setting final against budget is how you see which trades and variations drove the result and price the next project sharper.",
      moduleLabel: "Reports",
      moduleLabelKey: "nav.reports",
      to: "/reports",
    },
  ],
};

export default playbook;
