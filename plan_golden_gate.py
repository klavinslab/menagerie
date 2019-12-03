import sys
import os
import warnings
warnings.filterwarnings('ignore')

from util.plans import Cursor
from util.cloning_plans import CloningPlan
from util.plasmid_assembly_legs import GoldenGateLeg, SangerSeqLeg

from util.plan_tests import test_plan
from util.user_input import get_input

inputs = {
    "plan_path": "golden_gate_test",
    "aq_instance": "nursery"
}
# inputs = get_input(start_date=False)

plan = CloningPlan(inputs['plan_path'], inputs['aq_instance'])

cursor = Cursor(y=8)

n_seqs = 3

for step_id in plan.step_ids():
    plan_step = plan.step(step_id)

    txns = plan_step.transformations
    for txn in txns:
        src = txn['source']
        for dst in txn['destination']:
            gg_leg = GoldenGateLeg(plan_step, cursor)
            gg_leg.set_sample_io(src, dst)
            aq_plan_objs = gg_leg.add()
            upstr_op = gg_leg.get_output_op()

            for i in range(n_seqs):
                ss_leg = SangerSeqLeg(plan_step, cursor)
                ss_leg.set_sample_io(src, dst)
                aq_plan_objs = ss_leg.add()
                dnstr_op = ss_leg.get_input_op()
                ss_leg.wire_ops(upstr_op, dnstr_op)
                cursor.incr_x()
                cursor.incr_y(ss_leg.length())

            cursor.return_y()

plan.create_aq_plan()
plan.add_data_associations()

url = plan.aq_plan.session.url + "/plans?plan_id={}".format(plan.aq_plan.id)
print("Created Plan: {}".format(url))
print("{} total operations.".format(len(plan.aq_plan.operations)))
print("{} total wires.".format(len(plan.aq_plan.wires)))

# cost = pplan.aq_plan.estimate_cost()

# Paths for regression testing the output plan against a reference.
# out_path = os.path.join(plan_test_path, 'plan.json')
# ref_path = os.path.join(plan_test_path, 'plan-ref.json')

# test_plan(plan, out_path, ref_path)