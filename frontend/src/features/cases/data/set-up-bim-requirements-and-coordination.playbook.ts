// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up BIM requirements and coordination".
//
// Write down what information the employer actually needs from the models, set
// the federation and coordination rhythm that will deliver it, then check the
// models that come back carry the properties you asked for.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "set-up-bim-requirements-and-coordination",
  order: 324,
  category: "bim",
  companyTypes: ["bim-consultant", "designer", "general-contractor"],
  icon: "Combine",
  titleKey: "cases.set_up_bim_requirements_and_coordination.title",
  titleDefault: "Set up BIM requirements and coordination",
  descKey: "cases.set_up_bim_requirements_and_coordination.desc",
  descDefault:
    "Write down what information the employer actually needs from the models, set the federation and coordination rhythm that will deliver it, then check the models that come back carry the properties you asked for.",
  estMinutes: 10,
  steps: [
    {
      id: "requirements",
      icon: "ListChecks",
      inputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.requirements.in.brief",
          label: "Employer brief",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.requirements.in.standards",
          label: "Applicable standards",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.requirements.out.matrix",
          label: "Requirements matrix",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.requirements.out.properties",
          label: "Property schedule",
        },
      ],
      titleKey:
        "cases.set_up_bim_requirements_and_coordination.step.requirements.title",
      titleDefault: "Capture the information requirements",
      whatKey:
        "cases.set_up_bim_requirements_and_coordination.step.requirements.what",
      whatDefault:
        "Record the employer information requirements as a matrix: which models, at which stages, carrying which properties and to whose standard.",
      whyKey:
        "cases.set_up_bim_requirements_and_coordination.step.requirements.why",
      whyDefault:
        "A model handed over without the properties someone needs is a pretty picture, not an asset. Writing the requirement down first is what makes it something you can hold a designer to.",
      moduleLabel: "Requirements matrix",
      moduleLabelKey: "nav.eir_matrix",
      to: "/requirements/matrix",
    },
    {
      id: "coordinate",
      icon: "Layers",
      inputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.coordinate.in.matrix",
          label: "Requirements matrix",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.coordinate.in.models",
          label: "Discipline models",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.coordinate.out.federation",
          label: "Model federation",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.coordinate.out.cadence",
          label: "Coordination schedule",
        },
      ],
      titleKey:
        "cases.set_up_bim_requirements_and_coordination.step.coordinate.title",
      titleDefault: "Set the coordination cadence",
      whatKey:
        "cases.set_up_bim_requirements_and_coordination.step.coordinate.what",
      whatDefault:
        "Set up the federation and the regular coordination cycle against those requirements: who issues what, when the models come together and how often the team meets to clear conflicts.",
      whyKey:
        "cases.set_up_bim_requirements_and_coordination.step.coordinate.why",
      whyDefault:
        "Coordination that happens when someone remembers to do it happens too late. A fixed cadence tied to the requirements keeps the disciplines in step instead of colliding on site.",
      moduleLabel: "Coordination",
      moduleLabelKey: "nav.coordination_hub",
      to: "/coordination",
    },
    {
      id: "confirm",
      icon: "ShieldCheck",
      inputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.confirm.in.models",
          label: "Delivered models",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.confirm.in.matrix",
          label: "Requirements matrix",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.confirm.out.check",
          label: "Compliance check",
        },
        {
          labelKey:
            "cases.set_up_bim_requirements_and_coordination.step.confirm.out.gaps",
          label: "Property gaps flagged",
        },
      ],
      titleKey:
        "cases.set_up_bim_requirements_and_coordination.step.confirm.title",
      titleDefault: "Confirm the models comply",
      whatKey:
        "cases.set_up_bim_requirements_and_coordination.step.confirm.what",
      whatDefault:
        "Open the delivered models in the viewer and check the elements actually carry the properties, classifications and level of detail the requirements called for.",
      whyKey: "cases.set_up_bim_requirements_and_coordination.step.confirm.why",
      whyDefault:
        "The requirement only means something if you check against it. Catching a model short on properties at delivery is a re-issue; catching it at handover is a scramble to rebuild data nobody kept.",
      moduleLabel: "BIM viewer",
      moduleLabelKey: "nav.bim",
      to: "/projects/:projectId/bim",
    },
  ],
};

export default playbook;
