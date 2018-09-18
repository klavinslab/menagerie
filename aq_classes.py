import json
import copy

import pydent
from pydent import models
from pydent.models import Sample
from pydent.exceptions import AquariumModelError

def get_obj_by_name(leg, name):
    ops = [x for x in leg if x["name"] == name]
    if ops: return ops[0]


class Leg:

    leg_order = []
    primary_handles = []

    def __init__(self, plan_step, cursor):
        self.plan_step = plan_step
        self.ext_plan = self.plan_step.plan
        self.aq_plan = self.ext_plan.aq_plan
        self.session = self.ext_plan.session
        self.cursor = cursor
        self.create_operations()
        self.set_container_types()

        # This is no longer a good name for this variable.
        self.sample_io = {}


    # Does it make sense to populate this intermediate object?
    # Why not just build the array of operations?
    def create_operations(self):
        self.op_data = []
        self.wires = []

        for ot_name in self.leg_order:
            od = copy.deepcopy(get_obj_by_name(self.ext_plan.defaults, ot_name))
            od = od or { "defaults": {} }
            od["operation"] = self.initialize_op(ot_name)
            od["name"] = od["operation"].operation_type.name

            if self.op_data:
                self.wire_internal(self.op_data[-1]["operation"], od["operation"])

            self.op_data.append(od)
            self.cursor.decr_y()

    def set_container_types(self):
        # with open(aq_defaults_path, "r") as f:
        #     aq_defaults = json.load(f)
        default_container_types = self.ext_plan.aq_defaults["container_types"]

        for od in self.op_data:
            name = od["name"]
            ct = copy.deepcopy(get_obj_by_name(default_container_types, name))

            if ct:
                ct.pop("name")
            else:
                ct = {}

            od["container_types"] = ct

    def get_container(self, op_name, io_name, role, container_opt=None):
        ctypes = get_obj_by_name(self.op_data, op_name)["container_types"].get(io_name)

        if ctypes:
            container_name = ctypes[role + "_container_type"]

            if isinstance(container_name, dict):
                if container_opt:
                    container_name = container_name[container_opt]

                else:
                    raise Exception("Option required to specify container: " + container_name)

            return self.session.ObjectType.where({"name": container_name})[0]

    def add(self, container_opt=None):
        self.set_io(container_opt)
        self.aq_plan.add_operations([od["operation"] for od in self.op_data])
        self.aq_plan.add_wires(self.wires)
        print("### " + str(len(self.aq_plan.operations)) + " total operations")
        print()

    def set_io(self, container_opt):
        for i in range(len(self.op_data)):
            od = self.op_data[i]
            op = od["operation"]

            step_defaults = od["defaults"]
            this_io = { **step_defaults, **self.sample_io }

            for ft in op.operation_type.field_types:
                io_object = this_io.get(ft.name)

                is_sample = isinstance(io_object, Sample)
                is_array = isinstance(io_object, list)

                if is_sample or is_array:
                    container = self.get_container(op.operation_type.name, ft.name, ft.role, container_opt)
                    if is_sample:
                        try:
                            op.set_field_value(ft.name, ft.role, sample=io_object, container=container)
                        except AquariumModelError as e:
                            print("%s: %s" % (od["name"], e))

                    else:
                        values = [{
                            "sample": io_object.pop(0),
                            "container": container
                        }]

                        try:
                            op.set_field_value_array(ft.name, ft.role, values)
                        except AquariumModelError as e:
                            print("%s: %s" % (od["name"], e))

                        for obj in io_object:
                            try:
                                op.add_to_field_value_array(ft.name, ft.role, sample=obj, container=container)
                            except AquariumModelError as e:
                                print("%s: %s" % (od["name"], e))

                else:
                    try:
                        op.set_field_value(ft.name, ft.role, value=io_object)
                    except AquariumModelError as e:
                        print("%s: %s" % (od["name"], e))

            self.propagate_sample(self.op_data[i - 1]["operation"], self.op_data[i]["operation"])

            print("Set IO for " + od["name"])

    def initialize_op(self, ot_name):

        if isinstance(ot_name, str):
            ot_attr = {"name": ot_name}
        elif isinstance(ot_name, dict):
            ot_attr = ot_name

        ot_attr["deployed"] = True
        op_types = self.session.OperationType.where(ot_attr)

        if len(op_types) != 1:
            msg = "Didn't find a unique Operation Type for %s: %s"
            ots = [ot.category + " > " + ot.name for ot in op_types]
            print(msg % (ot_attr["name"], ots))

        op_type = op_types[0]
        op = op_type.instance()
        op.x = self.cursor.x
        op.y = self.cursor.y

        return op

    def wire_internal(self, upstr_op, dnstr_op):
        wire = self.get_wire_pair(upstr_op, dnstr_op)
        if not None in wire:
            self.wires.append(wire)

    def wire_ops(self, upstr_op, dnstr_op):
        wire_pair = self.get_wire_pair(upstr_op, dnstr_op)
        self.aq_plan.add_wires([wire_pair])
        self.propagate_sample(upstr_op, dnstr_op)

    def wire_input_array(self, upstr_ops, dnstr_op):
        dnstr_fvs = self.primary_io_array(dnstr_op, "input")

        for upstr_op in upstr_ops:
            w0 = self.primary_io(upstr_op, "output")
            w1 = [fv for fv in dnstr_fvs if fv.sample.name == w0.sample.name][0]
            wire_pair = [w0, w1]
            self.aq_plan.add_wires([wire_pair])

    # This method may be redundant
    def propagate_sample(self, upstr_op, dnstr_op):
        upstr_sample = None

        for h in self.primary_handles:
            try:
                fv = upstr_op.input(h)
            except:
                fv = None

            if fv:
                upstr_sample = fv.sample

        if upstr_sample:
            for h in self.primary_handles:
                fv = dnstr_op.input(h)
                if fv:
                    # TODO: don't override samples that are already set
                    try:
                        fv.set_value(sample=upstr_sample)
                    except AquariumModelError as e:
                        print("%s: %s" % (dnstr_op.operation_type.name, e))

    def get_wire_pair(self, upstr_op, dnstr_op):
        w0 = self.primary_io(upstr_op, "output")
        w1 = self.primary_io(dnstr_op, "input")
        return [w0, w1]

    def primary_io(self, op, role):
        fvs = self.primary_io_array(op, role)
        if fvs: return fvs[0]

    def primary_io_array(self, op, role):
        return [fv for fv in op.field_values if fv.role == role and fv.name in self.primary_handles]

    def select_op(self, ot_name):
        if isinstance(ot_name, dict):
            ot_name = ot_name["name"]

        selected = [od for od in self.op_data if od["operation"].operation_type.name == ot_name]
        if selected: return selected[0]["operation"]

    def get_output_op(self):
        return self.get_op_by_index(-1)

    def get_input_op(self):
        return self.get_op_by_index(0)

    def get_op_by_index(self, i):
        if self.leg_order:
            ot_name = self.leg_order[i]

            if isinstance(ot_name, dict):
                ot_name = ot_name["name"]

            return self.select_op(ot_name)

    def set_start_date(self, start_date):
        op = self.get_input_op()
        v = "{ \"delay_until\": \"%s\" }" % start_date
        op.set_field_value("Options", "input", value=v)

    @classmethod
    def length(cls):
         return len(cls.leg_order)


class Cursor:
    def __init__(self, x=None, y=None):
        self.x = x or 64
        self.x_incr = 192

        self.y = y or 1168
        self.y_incr = 64

        self.x_home = self.x
        self.max_x = self.x
        self.min_x = self.x

        self.y_home = self.y
        self.max_y = self.y
        self.min_y = self.y

    def set_x(self, x):
        self.x = x
        self.update_max_min_x()

    def set_y(self, y):
        self.y = y
        self.update_max_min_y()

    def set_xy(self, x, y):
        self.set_x(x)
        self.set_y(y)
        self.update_max_min()

    def incr_x(self, mult=1):
        self.x += mult * self.x_incr
        self.update_max_x()

    def decr_x(self, mult=1):
        self.x -= mult * self.x_incr
        self.update_min_x()

    def incr_y(self, mult=1):
        self.y += mult * self.y_incr
        self.update_max_y()

    def decr_y(self, mult=1):
        self.y -= mult * self.y_incr
        self.update_min_y()

    def set_x_home(self, x=None):
        self.x_home = x or self.x

    def return_x(self):
        self.x = self.x_home

    def set_y_home(self, y=None):
        self.y_home = y or self.y

    def return_y(self):
        self.y = self.y_home

    def set_home(self):
        self.set_x_home()
        self.set_y_home()

    def return_xy(self):
        self.return_x()
        self.return_y()

    def update_max_x(self):
        if self.x > self.max_x:
            self.max_x = self.x

    def update_min_x(self):
        if self.x < self.min_x:
            self.min_x = self.x

    def update_max_y(self):
        if self.y > self.max_y:
            self.max_y = self.y

    def update_min_y(self):
        if self.y < self.min_y:
            self.min_y = self.y

    def update_max_min_x(self):
        self.update_max_x()
        self.update_min_x()

    def update_max_min_y(self):
        self.update_max_y()
        self.update_min_y()

    def update_max_min(self):
        self.update_max_min_x()
        self.update_max_min_y()

    def get_xy(self):
        return [self.x, self.y]

    def advance_to_next_step(self):
        self.set_xy(self.min_x, self.min_y)
        self.decr_y()
        self.set_home()
