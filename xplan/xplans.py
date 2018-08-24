import json
import re
import os

from plans import ExternalPlan, PlanStep, Transformation

import pydent
from pydent import models
from pydent.models import Sample

class XPlan(ExternalPlan):
    def __init__(self, aq_plan_name, aq_instance):
        super().__init__(aq_plan_name, aq_instance)

        self.steps = [XPlanStep(self, s) for s in self.plan['steps']]

        self.input_samples = {}
        for plan_id, aq_id in self.plan_params['input_samples'].items():
            if plan_id == "library_composition":
                aq_ids = aq_id["components"]
                component_samples = []

                for ai in aq_ids:
                    component_samples.append(self.find_input_sample(ai))

                aq_id["components"] = component_samples
                found_input = aq_id

            else:
                found_input = self.find_input_sample(aq_id)

            self.add_input_sample(plan_id, found_input)

        # Assumes that there is only one source and only one dna_seq_step
        self.ngs_samples = self.dna_seq_steps()[0].measured_samples

        # self.set_default_protease()

    def find_input_sample(self, aq_id):
        if isinstance(aq_id, int):
            attr = 'id'
        else:
            attr = 'name'

        return self.session.Sample.where({attr: aq_id})[0]

    def add_input_sample(self, plan_id, sample):
        self.input_samples[plan_id] = sample

    def get_steps_by_type(self, type):
        return [s for s in self.steps if s.operator_type == type]

    def provision_steps(self):
        return self.get_steps_by_type('provision')

    def dna_seq_steps(self):
        return self.get_steps_by_type('dna_seq')

    def step_ids(self, steps=None):
        steps = steps or self.steps
        return sorted([s.step_id for s in steps])

    ##### These are probably unique to protein stability #####

    # def set_default_protease(self):
    #     def_prot_pat = re.compile(r'protease_1', re.IGNORECASE)

    #     possible_defaults = self.raw_protease_inputs()
    #     test = [s for s in possible_defaults if re.search(def_prot_pat, s)]

    #     if test:
    #         unprovisioned = test[0]

    #     else:
    #         unprovisioned = possible_defaults[0]

    #     self.default_protease = self.get_provisioned(unprovisioned)

    # def raw_protease_inputs(self):
    #     protease_inputs = []
    #     prot_pat = re.compile(r'protease', re.IGNORECASE)

    #     for t in self.provision_steps()[0].transformations:
    #         for s in t.source:
    #             if re.search(prot_pat, s['sample']):
    #                 protease_inputs.append(s['sample'])

    #     return list(set(protease_inputs))

    def protease_sample(self, s):
        return isinstance(s, Sample) and s.sample_type.name == "Protease"

    def prov_protease_inputs(self):
        return {k:s for (k,s) in self.input_samples.items() if self.protease_sample(s)}

    def get_provisioned(self, unprovisioned):
        txns = self.provision_steps()[0].transformations
        provisioned = [t for t in txns if t.source[0]['sample'] == unprovisioned][0]
        return provisioned.destination[0]['sample']


class XPlanStep(PlanStep):
    def __init__(self, plan, plan_step):
        super().__init__(plan, plan_step)
        self.plan = plan
        self.plan_step = plan_step

        self.step_id = self.plan_step['id']
        self.name = self.plan_step['name']
        self.operator = self.plan_step['operator']
        self.operator_type = self.operator['type']

        self.transformations = []
        for txn in self.operator.get('transformations', []):
            self.transformations.append(XPlanTransformation(self, txn))

        self.measurements = []
        for msmt in self.operator.get('measurements', []):
            self.measurements.append(XPlanMeasurement(self, msmt))

        self.measured_samples = [m.source for m in self.measurements]

        self.output_operations = {}

        # self.flow_samples = [m.source for m in self.measurements if m.file.endswith('.fcs')]

    def yeast_inputs(self):
        yeast_handles = ["DNA Library", "Yeast Strain"]
        yeast_inputs = []

        for h in yeast_handles:
            yeast_inputs.extend(self.get_inputs(h))

        return yeast_inputs

    def add_output_operation(self, uri, op):
        self.output_operations[uri] = op

    # TODO: Need to make this sort for the GUI layout.
    def get_sorted_transformations(self):
        txns = self.operator.get('transformations')
        return txns


class XPlanTransformation(Transformation):
    def __init__(self, plan_step, transformation):
        super().__init__(plan_step, transformation)
        self.source = self.format(transformation['source'])
        self.destination = self.format(transformation['destination'])

    def source_samples(self):
        return [x['sample'] for x in self.source]

    def destination_samples(self):
        return [x['sample'] for x in self.destination]

    def protease(self):
        provisioned = self.plan.prov_protease_inputs()
        proteases = [x for x in self.source if x['sample'] in provisioned.keys()]

        if proteases:
            return proteases[0]
        else:
            return {}

    def yeast(self):
        return [x for x in self.source_samples() if x in self.plan_step.yeast_inputs()]

    @staticmethod
    def format(element):
        if isinstance(element, list):
            return [{ 'sample': e } if isinstance(e, str) else e for e in element]

        elif isinstance(element, dict):
            return [element]

        elif isinstance(element, str):
            return [{ 'sample': element }]

        else:
            raise Exception('Format of %s not recognized' % str(element))


class XPlanMeasurement():
    def __init__(self, plan_step, measurement):
        self.plan_step = plan_step
        self.plan = self.plan_step.plan
        self.source = measurement['source']
        self.file = measurement['file']
