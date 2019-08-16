#!/usr/bin/env python

import rospy
from owlready2 import *

import actionlib

from cheops_system_state_msgs.msg import SystemState
from cheops_graph_manipulation_msgs.msg import GraphManipulationActionAction

# Load tomasys and abb_scenario2 ontologies
onto_path.append("../../../mc_mdl_tomasys/") # local folder to search for ontologies
onto_path.append("../../../mc_mdl_abb/") # local folder to search for ontologies
# TODO back to relative paths adapting the launchfile
tomasys = get_ontology("/home/chcorbato/abb_mros/src/mc_mdl_tomasys/tomasys.owl").load()
onto = get_ontology("/home/chcorbato/abb_mros/src/mc_mdl_abb/abb_scenario2.owl").load()

def obtainBestFunctionDesign(o):
    f = o.typeF
    # get fds for Function F
    fds = []
    for fd in list(tomasys.FunctionDesign.instances()):
        if fd.solves == f:
            fds.append(fd)
    print("\nFunctionDesigns available for obj: ",fds)
    aux = 0
    best_fd = None
    for fd in fds:
        # FILTER if FD realisability is NOT FALSE (TODO check SWRL rules are complete for this)
        print("FD ", fd, fd.fd_realisability)
        if fd.fd_realisability != False:
            # FILTER if the FD error log does NOT contain the current objective
            print("Fd: ", fd, "error_log: ", fd.fd_error_log)
            if not o in fd.fd_error_log:
                if fd.fd_efficacy > aux:
                    best_fd = fd
                    aux = fd.fd_efficacy
    if ( best_fd == None ):
        print("*** OPERATOR NEEDED, NO SOLUTION FOUND ***")
        return None
    else:
        print("\nBest FD available", best_fd)
        return best_fd

'''
To solve the given Objective, recursively Grounds the required hierarchy of
sub-Objectives and Function Groundings
'''
def groundObjective(o, cspecs):
    print("=> Reasoner grounding objective: ", o)
    fd = obtainBestFunctionDesign(o)
    if( fd == None ):
        print("*** Objective ", o,"cannot be realised ***")
        return ["safe_shutdown"]
    fg = tomasys.FunctionGrounding("fg_" + fd.name)
    print("Roles: ",fd.roles)
    for r in fd.roles:
        b = tomasys.Binding("b_" + r.name)
        b.binding_role = r
        fg.has_bindings = b # TODO also ad the binding_component
        cspecs.append(r.roleDef)
    for f in fd.requires:
        print("Requires: ", fd.requires)
        ob = tomasys.Objective("o_" + f.name)
        ob.typeF = f
        fg.needs.append(ob)
        groundObjective(ob, cspecs)
    return cspecs

'''
Initiatize the reasoner Kknowledge base: load ontology and asserts initial state
'''
def init_kb():
    global onto
    print("HEREEE")
    # Initial system state
    fd = onto.search(iri = "*fd_build_2arms")[0]
    f = onto.search(iri = "*f_build_pyramid")[0]
    yumi = onto.search(iri = "*#c_yumi")[0]
    role_yumi2 = onto.search(iri = "*r_yumi2a")[0]

    fg = tomasys.FunctionGrounding("fg_build2", namespace = onto)
    o = tomasys.Objective("o_build_pyramid", namespace = onto)
    b = tomasys.Binding(namespace = onto)
    b.binding_component = yumi
    b.binding_role = role_yumi2
    o.typeF = f
    fg.realises = o
    fg.typeFD = fd
    fg.hasBindings.append(b)


sys_state=None
graph_manipulation_client=None

def callback(msg):
    global sys_state
    sys_state = msg



def timer_cb(event):
    global sys_state
    global onto

    if not sys_state:
        rospy.logwarn_throttle(1., 'Still waiting on system state ..')
        return

    if sys_state.yumi_status != 1:
        c = onto.search(iri="*#c_yumi")[0]
        c.c_status = False
        print("Yumi in ERROR")
    if sys_state.camera_status != 1:
        print("Camera in ERROR")
        c = onto.search(iri="*c_camera")[0]
        c.c_status = False
    if sys_state.tag_detection_status != 1:
        print("Tag not detected")
        f = onto.search(iri="*f_detect_tag_poses")[0]
        # for o in list(tomasys.Objective.instances() ):
        #     if (o.typeF == f):
        #         o.c_status = False

    rospy.loginfo_throttle(1., 'camera: {}, tag_detect: {}, yumi: {}'.format(
        sys_state.camera_status, sys_state.tag_detection_status, sys_state.yumi_status))

    # TODO CHECK: update reasoner facts, evaluate, retrieve action, publish
    # update reasoner facts
    sync_reasoner_pellet(infer_property_values = True, infer_data_property_values = True)

    # PRINT system status
    print("\nComponents Statuses:")
    for i in list(tomasys.ComponentState.instances()) :
        print(i, i.c_status)

    print("\nBindings Statuses:")
    for i in list(tomasys.Binding.instances()) :
        print(i, i.b_status)

    print("\nFG Statuses:")
    for i in list(tomasys.FunctionGrounding.instances()) :
        print(i, i.fg_status)

    print("\nObjectives Statuses:")
    for i in list(tomasys.Objective.instances()) :
        print(i, i.o_status)

    print("\nCC availability:")
    for i in list(tomasys.ComponentClass.instances()) :
        print(i, i.cc_availability)

    print("\nFD realisability:")
    for i in list(tomasys.FunctionDesign.instances()) :
        print(i, i.fd_realisability)


    # evaluate and retrieve desired configuration
    # init objectives in error
    objectives_in_error = []
    for o in list(tomasys.Objective.instances() ):
        if not o.o_status == True:
            objectives_in_error.append(o)
    print("\nObjectives in error:", objectives_in_error)
    # Ground a solution hierarchy for each root objective in error. We assume here that root_objectives do not share intermediate objectives
    cspecs = []
    for o in objectives_in_error:
        groundObjective(o, cspecs)

    # Retrieve action and publish from cspecs
    str_specs = []
    for cs in cspecs:
        str_specs.append(cs.name)
    print("RESULT CONFIG: ", str_specs)
    request_reconfiguration(str_specs)

def request_reconfiguration(component_specs):

    return


if __name__ == '__main__':
    rospy.init_node('mros1_reasoner')

    sub = rospy.Subscriber('system_state', SystemState, callback)

    init_kb()
    #for testing YUMI in error
    sys_state = SystemState(yumi_status = 99, camera_status = 1, tag_detection_status = 1)

    timer = rospy.Timer(rospy.Duration(10.), timer_cb)

    graph_manipulation_client = actionlib.SimpleActionClient(
            'cheops_graph_manipulation_action_server',
            GraphManipulationActionAction)
    graph_manipulation_client.wait_for_server()

    rospy.spin()
