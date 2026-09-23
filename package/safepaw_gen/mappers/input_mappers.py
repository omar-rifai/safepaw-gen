from ..data_models.input_models import Instance, Facility, Region, Resource, PatientsGroup, CaseMixRatios, QualityBounds, TreatmentBounds


def validate_required_params(params, required_keys, msg):
    missing = [k for k in required_keys if k not in params]
    if missing:
        raise KeyError(f"Missing required parameters: {missing}. {msg}")


def create_json_from_patients(list_patients: list, params_system: dict) -> dict:
    """ Adds group ids  (G) to params_system"""
    params_system["G"] = list(dict.fromkeys(x.id for x in list_patients))
    return params_system


def reconstruct_L_from_resources(list_resources: list, params_system: dict) -> dict:
    """ Adds Resource types (L) to params_system"""
    params_system["L"] = [r.id for r in list_resources]
    return params_system

def reconstruct_delta_l_from_resources(list_resources: list, params_system: dict) -> dict:
    """ Adds delta_l (Transfer unit for each resource type l) to params_system"""
    params_system["delta_l"] = {r.id: r.transfer_unit for r in list_resources}
    return params_system


def reconstruct_I_gu(list_pathways: list, params_system: dict) -> dict:
    """ Adds Set of pathways available to group g that fall under care quality level u to params_system"""
    validate_required_params(params_system, ["G"], "Construct patient groups first.")       
    I_gu = {}
    for g in params_system["G"]:
        I_g = {}
        for u in params_system["U_idx"][g]:
            I_g[u] = [k.id for k in [x for x in list_pathways if x.group_id == g] if k.quality_level==u]
        I_gu[g] = I_g
    params_system["I_gu"] = I_gu
    return params_system


def reconstruct_c_gk(list_pathways: list, params_system: dict) -> dict:
    """ Adds c_gk ( Benefit score of assigning a patient from group g with the care pathway k) to params_system"""
    validate_required_params(params_system, ["G"], "Construct patient groups first.")
    c_gk = {}
    for g in params_system["G"]:
        c_gk[g] = {k.id: k.group_benefit for k in [k for k in list_pathways if k.group_id == g]}
    params_system["c_gk"] = c_gk
    return params_system


def reconstruct_U_from_pathways(list_pathways: list, params_system: dict) -> dict:
    """ Adds U (Quality level u among the Ug quality levels of care pathways of group g) to params_system"""
    validate_required_params(params_system, ["G"], "Construct patient groups first.")
    U_idx = {}
    for g in params_system["G"]:
        U_idx[g] = list(set([k.quality_level for k in list_pathways if k.group_id == g]))
    params_system["U_idx"] =  U_idx
    return params_system


def reconstruct_O_gk(list_facilities: list, params_system: dict) -> dict:
    """ Adds O_g,k (Set of healthcare facilities able to treat patient group g following pathway k) to params_system"""
    validate_required_params(params_system, ["K_idx", "G"], "Construct patient groups and pathways first")
    O = {}    
    for g in params_system["G"]:
        O_g = {}
        for k in params_system["K_idx"][g]:
            O_g[k] = [h.id for h in list_facilities if k in h.available_pathways]
        O[g] = O_g
    params_system["O_gk"] = O
    return params_system


def reconstruct_J_h(list_facilities: list, params_system: dict) -> dict:
    """ Adds J_h (Set of healthcare facilities to which patients from facility h can be transferred) to params_system"""
    J = {}
    for h in list_facilities:
        J[h.id] = [f for f in h.linked_facilities]
    params_system["J_h"] = J
    return params_system


def reconstruct_b_hl(list_facilities: list, params_system: dict) -> dict:
    """ Adds b_hl_in and b_hl_out (Maximum proportions of resource type l transferable to and from facility h) to params_system"""
    b_hl_in = {}
    b_hl_out = {}
    for h in list_facilities:
        b_hl_in[h.id] = {}
        b_hl_out[h.id] = {}
        for l in params_system["L"]:
            if l in h.resources_capacity.keys():
                b_hl_in[h.id][l] = h.max_transferable_in[l]
                b_hl_out[h.id][l] = h.max_transferable_out[l]
    params_system["b_hl_in"] = b_hl_in
    params_system["b_hl_out"] = b_hl_out
    return params_system


def reconstruct_t_gkal(list_activities: list, params_system: dict) -> dict:
    """Adds t_gkal (Consumption of resource l required to perform care activity a of pathway k of group g) to params_system"""
    validate_required_params(params_system, ["G", "K_idx"], "Construct patient groups and pathways first.")
    t = {g : {k: {} for k in params_system["K_idx"][g]} for g in params_system["G"]}  

    for a in list_activities:
        g, k =  a.group_id, a.associated_pathway
        t[g][k][a.id] = a.required_resources 
    
    params_system["t_gkal"] = t
    return params_system


def reconstruct_wrh(list_regions: list, params_system: dict) -> dict:
    """ Adds w_rh (Preference of patient group g originating from region r to receive care in facility h) 
    to params_system"""
    w = {}
    for r in list_regions:
        w[r.id] = r.facilities_affinity
    params_system["w_rh"] = w
    return params_system


def reconstruct_A_gk_from_activities(list_activities: list, params_system: dict) -> dict:
    """ Adds A_gk (num activities for pathway k of group g) to params_system"""
    validate_required_params(params_system, ["K_idx"], "Construct pathways first.")
    
    A = {g: {k: 0 for k in params_system["K_idx"][g]} for g in params_system["G"]}
    A_idx = {g: {k: [] for k in params_system["K_idx"][g]} for g in params_system["G"]}

    for a in list_activities:
        g, k = a.group_id, a.associated_pathway
        if g in A and k in A[g]:
            A[g][k] += 1
            A_idx[g][k].append(a.id)
    params_system["A_gk"] = A
    params_system["A_idx"] = A_idx
    return params_system

def reconstruct_Kg_from_pathways(list_pathways: list, params_system: dict) -> dict:
    """Adds K_g (Pathways for each patient group G) to params_system"""
    validate_required_params(params_system, ["G"], msg="Construct patient groups first")
    K_g = {}
    K_idx = {}
    for g in params_system["G"]:
        K_g[g] = len([n for n in list_pathways if n.group_id == g])
        K_idx[g] = [n.id for n in list_pathways if n.group_id == g]
    params_system["K_g"] = K_g 
    params_system["K_idx"] = K_idx
    return params_system



def get_K_idx(list_pathways: list, params_system: dict) -> dict:
    """ Adds list of pathways ids for each patient group G to params_system"""
    validate_required_params(params_system, ["G"], msg="Construct patient groups first")
    K_idx = {}
    for g in params_system["G"]:
        K_idx[g] = [n.id for n in list_pathways if n.group_id == g]
    params_system["K_idx"] = K_idx
    
    return params_system


def reconstruct_N_gka(list_activities: list, params_system: dict):
    """
    (1) N_gka_1: All activities of pathway k of group g to be considered for potential transfers
    (2) N_gka_2: Next activity a to be considered for potential transfers after activity a of pathway k of group g
    """
    validate_required_params(params_system, ["G", "K_idx"], msg="Construct patient groups first")
    B = {g: {k: [] for k in params_system["K_idx"][g]} for g in params_system["G"]}
    N = {g: {k: {} for k in params_system["K_idx"][g]} for g in params_system["G"]}

    for a in list_activities:
        if not a.transferable:
            continue
        g, k = a.group_id, a.associated_pathway
        B[g][k].append(a.id)      
        N[g][k][a.id] = a.transfer_to
        
    params_system["N_gka_1"] = B
    params_system["N_gka_2"] = N
    return params_system

def reconstruct_m_hl(list_facilities: list, params_system: dict) -> dict:
    """ Adds m_hl (Total capacity of resource type l in healthcare facilities h) to params_system"""
    m = {}
    
    for h in list_facilities:
        m[h.id] = {l: v for l, v in h.resources_capacity.items()}
    params_system["m_hl"] = m
    return params_system


def create_metadata(params_system: dict, list_facilities: list[Facility], list_regions: list[Region], instance) -> dict:
    """Create dictionary with metadata from the problem instance not used in the optimization model"""
    params_system["global_multiplier_capacity"] = instance.global_multiplier_capacity
    params_system["global_multiplier_demand"] = instance.global_multiplier_demand
    params_system["global_perc_transfers"] = instance.global_perc_transfers
    
    params_system["facilities_metadata"] = {h.id: {"lat": h.lat, "lon": h.lon, "name": h.name,
                                                            "id": h.id, "nbr_visits": h.nbr_visits, "region_id": h.region_id,
                                                            "type": h.facility_type}
                                                            for h in list_facilities} 
    params_system["regions_metadata"] = {r.id : {"dep_code": r.dep_code, "comm_code": r.comm_code, "can_code": r.can_code,  "lat": r.lat, "lon": r.lon}
                                        for r in list_regions}

    return params_system


def create_json_from_regions(list_regions: list, params_system: dict) -> dict:
    """Adds json parameters (R, w_rh) associated with a Region Object to params_system"""
    if "R" not in params_system:
        unique_ids = [r.id for r in list_regions]
        params_system["R"] = unique_ids
    if "w_rh" not in params_system:
        params_system = reconstruct_wrh(list_regions, params_system)
    return params_system

def create_json_from_resources(list_resources: list, params_system: dict) -> dict:
    """ Adds json parameters) associated with a Resource Object to params_system"""
    params_system = reconstruct_L_from_resources(list_resources, params_system)
    params_system = reconstruct_delta_l_from_resources(list_resources, params_system)
    return params_system


def create_json_from_activities(list_activities: list, params_system: dict) -> dict:
    """ Adds json parameters (A_gk, t_gkal, N_gka1, N_gka2) associated with a Activity Object to params_system"""
    params_system = reconstruct_A_gk_from_activities(list_activities, params_system)
    params_system = reconstruct_t_gkal(list_activities, params_system)
    params_system = reconstruct_N_gka(list_activities, params_system)
    return params_system

def create_json_from_facilities(list_facilities: list, params_system: dict) -> dict:
    """Adds json parameters (H, O_gk, J_h, b_hl, m_hl) associated with a Faciliy Object to params_system"""
    params_system["H"] = [x.id for x in list_facilities]
    params_system = reconstruct_O_gk(list_facilities, params_system)
    params_system = reconstruct_J_h(list_facilities, params_system)
    params_system = reconstruct_b_hl(list_facilities, params_system)
    params_system = reconstruct_m_hl(list_facilities, params_system)
    return params_system


def create_json_from_pathways(list_pathways: list, params_system: dict) -> dict:
    """ Adds json parameters (U, I_gu, Kg, c_gk, K_ids) associated with a Pathway Object to params_system"""
    params_system = reconstruct_U_from_pathways(list_pathways, params_system)
    params_system = reconstruct_I_gu(list_pathways, params_system)
    params_system = reconstruct_Kg_from_pathways(list_pathways, params_system)
    params_system = reconstruct_c_gk(list_pathways, params_system)
    params_system = get_K_idx(list_pathways, params_system)
    return params_system

def create_json_from_instance(instance: Instance,  params_system: dict) -> dict:  
    """ Adds json parameters ("D", mode, "p_transf" and "alpha")
    associated with an Instance object to params_system
    """
    params_system["D"] = instance.total_demand
    params_system["alpha"] = instance.alpha
    params_system["mode"] = instance.id
    params_system["dep_code"] = instance.dep_code
    params_system["p_transf"] = instance.perc_transfers
    return params_system 


def create_json_fromCaseMixRatios(list_case_mix_ratios: list[CaseMixRatios], params_system: dict) -> dict:
    """ Adds json parameters (d_gr) associated with a CaseMixRatios Object to params_system"""
    d_gr = {}
    for cmr in list_case_mix_ratios:
        if cmr.group_id not in d_gr:
            d_gr[cmr.group_id] = {}
        d_gr[cmr.group_id][cmr.region_id] = cmr.ratio

    params_system["d_gr"] = d_gr
    return params_system


def create_json_fromQualityBounds(list_quality_bounds: list[QualityBounds], params_system: dict) -> dict:
    """ Adds json parameters (under_q_g, over_q_g, under_q_gu, over_q_gu) associated with a QualityBounds Object to params_system"""
    under_q_gu = {}
    over_q_gu = {}
    for qb in list_quality_bounds:
        if qb.group_id not in params_system["G"]:
            continue
        if qb.group_id not in under_q_gu:
            under_q_gu[qb.group_id] = {}
            over_q_gu[qb.group_id] = {}  
        under_q_gu[qb.group_id][qb.quality_id] = qb.min_quality_bound
        over_q_gu[qb.group_id][qb.quality_id] = qb.max_quality_bound
      
    params_system["Under_q_gu"] = under_q_gu
    params_system["Over_q_gu"] = over_q_gu
    return params_system

def create_json_fromTreatmentBounds(list_treatment_bounds: list[TreatmentBounds], params_system: dict) -> dict:

    """ Adds json parameters (under_q_g, over_q_g, under_q_gu, over_q_gu) associated with a QualityBounds Object to params_system"""
    under_q_g = {}
    over_q_g = {}

    
    for tb in list_treatment_bounds:
        if tb.group_id not in params_system["G"]:
            continue
        under_q_g[tb.group_id] = tb.min_treatment_bound
        over_q_g[tb.group_id] = tb.max_treatment_bound
      
    params_system["Under_q_g"] = under_q_g
    params_system["Over_q_g"] = over_q_g    
    return params_system


def convert_dm_to_json(session, params_system: dict | None = None) -> dict:
    """Calls converters for Patients, Regions, Resources, Pathways, Activities, Facilities and Instances to json
    also removes utility parameters from params_system
    """
    from sqlmodel import select
    from ..data_models.input_models import Facility, Region, Resource, PatientsGroup, Pathway, Activity

    if params_system is None: params_system = {}
    list_facilities = session.exec(select(Facility)).all()
    list_regions = session.exec(select(Region)).all()
    list_activities = session.exec(select(Activity)).all()
    list_resources = session.exec(select(Resource)).all()
    list_patients = session.exec(select(PatientsGroup)).all()
    list_pathways = session.exec(select(Pathway)).all()
    list_instances = session.exec(select(Instance)).all()
    list_case_mix_ratios = session.exec(select(CaseMixRatios)).all()
    list_quality_bounds = session.exec(select(QualityBounds)).all()
    list_treatment_bounds = session.exec(select(TreatmentBounds)).all()


    params_system = create_json_from_patients(list_patients, params_system)
    params_system = create_json_from_regions(list_regions, params_system)
    params_system = create_json_from_resources(list_resources, params_system)
    params_system = create_json_from_pathways(list_pathways, params_system)
    params_system = create_json_from_facilities(list_facilities, params_system)
    params_system = create_json_from_activities(list_activities, params_system)
    params_system = create_json_from_instance(list_instances[0], params_system)
    params_system = create_json_fromCaseMixRatios(list_case_mix_ratios, params_system)
    params_system = create_json_fromQualityBounds(list_quality_bounds, params_system)
    params_system = create_json_fromTreatmentBounds(list_treatment_bounds, params_system)

    params_system = create_metadata(params_system, list_facilities, list_regions, list_instances[0])
    return params_system
