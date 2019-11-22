from plans import Leg

class ProtStabLeg(Leg):

    leg_order = []

    primary_handles = [
        'Yeast Culture',
        'Labeled Yeast Library',
        'Stored sample rep 1',
        'Stored sample rep 2'
    ]

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)

    def set_yeast(self, input_sample_uri):
        input_sample = self.ext_plan.input_sample(input_sample_uri)
        self.set_yeast_from_sample(input_sample)

    def set_yeast_from_sample(self, input_sample):
        for h in self.primary_handles:
            self.sample_io[h] = input_sample

    def get_innoculate_op(self):
        return self.select_op('Innoculate Yeast Library')

    # def set_uri(self, ot_name, obj):
    #     op = self.select_op(ot_name)
    #     obj.get('sample')


class OvernightLeg(ProtStabLeg):

    leg_order = ['Innoculate Yeast Library']

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)


class MixCulturesLeg(ProtStabLeg):

    leg_order = ['Mix Cultures']

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)

    def set_components(self, library_composition):
        self.sample_io["Component Yeast Culture"] = library_composition["components"]
        self.sample_io["Proportions"] = str(library_composition["proportions"])

    def wire_ops(self, upstr_fv, dnstr_fv):
        wire_pair = [upstr_fv, dnstr_fv]
        self.aq_plan.add_wires([wire_pair])


class NaiveLeg(ProtStabLeg):

    leg_order = ['Store Yeast Library Sample']

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)


class InductionLeg(ProtStabLeg):

    leg_order = ['Dilute Yeast Library']

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)


class TreatmentLeg(ProtStabLeg):

    leg_order = []

    treatment_sample_types = ['Protease', 'Biotinylated Binding Target']

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)

    def set_protease(self, source):
        for st in self.treatment_sample_types:
            protease_inputs = self.plan_step.get_inputs(st)
            if protease_inputs: break

        p = [s for s in source if self.plan_step.sample_key(s) in protease_inputs]

        if p:
            s = p[0]
            prot_samp =  self.ext_plan.input_sample(self.plan_step.sample_key(s))
            prot_conc = s['concentration']
        
        else:
            raise "protease not found"

        # else:
        #     prot_samp =  self.ext_plan.input_sample(self.ext_plan.default_protease)
        #     prot_conc = 0

        self.sample_io['Protease'] = prot_samp
        self.sample_io['Protease Concentration'] = prot_conc

        print(prot_samp.name + " " + str(prot_conc))


class SortLeg(TreatmentLeg):

    leg_order = (
        'Challenge and Label',
        'Sort Yeast Display Library',
        'Innoculate Yeast Library',
        'Store Yeast Library Sample'
    )

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)

        self.sample_io['Sort?'] = 'yes'


class FlowLeg(TreatmentLeg):

    leg_order = (
        'Challenge and Label',
        'Sort Yeast Display Library'
    )

    def __init__(self, plan_step, cursor):
        super().__init__(plan_step, cursor)

        self.sample_io['Sort?'] = 'no'
