from ..data_models.input_models import PatientsGroup, Region, Resource, Pathway, Facility, Activity, Instance, \
    CaseMixRatios, FacilityAffinity, FacilityResources, FacilityPathways, LinkedFacilities, ActivityResources, TreatmentBounds, QualityBounds

from sqlmodel import Session

def create_Patients_from_json(params_system: dict) -> list:
    """Returns list of Patient Objects from model params"""
    list_patients = []
    for g in params_system["G"]:
        list_patients.append(PatientsGroup(id=g))
    return list_patients

def create_Regions_from_json(params_system: dict) -> list:
    """Returns list of Region Objects from model params"""
    list_regions = []
    for r in params_system["R"]:
        list_regions.append(Region(id=r,
                                   lat=params_system["regions_metadata"][r]["lat"],
                                   lon=params_system["regions_metadata"][r]["lon"],
                                   dep_code=params_system["regions_metadata"][r]["dep_code"],
                                   comm_code=params_system["regions_metadata"][r]["comm_code"],
                                   can_code= params_system["regions_metadata"][r]["can_code"]))
    return list_regions

def create_Resources_from_json(params_system: dict) -> list:
    """Returns list of Resources Objects from model params"""
    list_resources = []
    for l in params_system["L"]:
        list_resources.append(Resource(id=l, transfer_unit=params_system["delta_l"][l]))
    return list_resources


def create_Pathways_from_json(params_system: dict) -> list:
    """Returns list of Pathway Objects from model params"""

    def get_quality_level(g,k):
        for u in params_system["U_idx"][g]:
            if k in params_system["I_gu"][g][u]:
                return u
    list_pathways = []
    for g in params_system["G"]:
        for k in params_system["K_idx"][g]:
                list_pathways.append(Pathway(id=k, group_id=g, quality_level=get_quality_level(g,k),
                                              group_benefit=params_system["c_gk"][g][k]))
    return list_pathways


def create_Facilities_from_json(params_system: dict) -> list:
    """Returns list of PatientsGroup Objects from model params"""
    list_facilities = []
    for h in params_system["H"]:
        list_facilities.append(Facility(id=h,
                                        name=params_system["facilities_metadata"][h]["name"],
                                        facility_type=params_system["facilities_metadata"][h]["type"],
                                        region_id=params_system["facilities_metadata"][h]["region_id"],
                                        lat=params_system["facilities_metadata"][h]["lat"],
                                        lon=params_system["facilities_metadata"][h]["lon"],
                                        nbr_visits=params_system["facilities_metadata"][h]["nbr_visits"]))
    return list_facilities

def create_Activities_from_json(params_system: dict) -> list:
    """Returns list of Activity Objects from model params"""
    list_activities = []
    for g in params_system["G"]:
        for k in params_system["K_idx"][g]:
            for a in params_system["A_idx"][g][k]:
                is_transferable = (a in params_system["N_gka_1"][g][k])
                transfer_to = None
                if is_transferable: transfer_to = params_system["N_gka_2"][g][k][a]
                list_activities.append(Activity(id=a,
                                                group_id=g,
                                                pathway_id=k, 
                                                transferable=is_transferable, 
                                                transfer_to=transfer_to))
    return list_activities

def create_Instance_from_json(params_system: dict) -> list:
    """Returns Instance Object from model params"""
    instance = Instance(id=params_system["mode"], total_demand=params_system["D"], dep_code=params_system["dep_code"],perc_transfers=params_system["p_transf"], alpha=params_system["alpha"],
                         global_multiplier_demand=params_system["global_multiplier_demand"], global_multiplier_capacity=params_system["global_multiplier_capacity"], global_perc_transfers=params_system["global_perc_transfers"] )
                        
    return instance


## Create relationships tables

def create_FacilityPathways(params_system: dict) -> list:
      
    facility_pathways = []
    for g in params_system["G"]:
        for k in params_system["K_idx"][g]:
                for h in params_system["H"]:
                    if h in params_system["O_gk"][g][k]:
                        facility_pathways.append(FacilityPathways(facility_id=h, group_id=g, pathway_id=k))
    return facility_pathways


def create_CaseMixRatios(params_system: dict) -> list:
    case_mix_ratios = []
    for g in params_system["G"]:
        for r in params_system["R"]:
            case_mix_ratios.append(CaseMixRatios(group_id=g, region_id=r, ratio=params_system["d_gr"][g][r]))      
    return case_mix_ratios


def create_FacilityAffinity(params_system: dict) -> list:
    facility_affinity = []
    for h in params_system["H"]:
        for r in params_system["R"]:
            facility_affinity.append(FacilityAffinity(facility_id=h, region_id=r, affinity_score=params_system["w_rh"][r][h]))      
    return facility_affinity

def create_FacilityResources(params_system: dict) -> list:
    facility_resources = []
    for h in params_system["H"]:
        for l in params_system["L"]:
            facility_resources.append(FacilityResources(facility_id=h, resource_id=l, capacity=params_system["m_hl"][h][l],
                                                       max_transferable_in=params_system["b_hl_in"][h][l], 
                                                       max_transferable_out=params_system["b_hl_out"][h][l]))      
    return facility_resources

def create_LinkedFacilities(params_system: dict) -> list:
    linked_facilities = []
    for h in params_system["H"]:
        for h2 in params_system["H"]:
            if h2 in params_system["J_h"][h]:
                linked_facilities.append(LinkedFacilities(facility_id=h, linked_facility_id=h2))      
    return linked_facilities

def create_ActivityResources(params_system: dict) -> list:
    activity_resources = []
    for g in params_system["G"]:
        for k in params_system["K_idx"][g]:
            for a in params_system["A_idx"][g][k]:
                for l in params_system["L"]:
                    if l in params_system["t_gkal"][g][k][a]:
                        activity_resources.append(ActivityResources(activity_id=a, pathway_id=k, group_id=g, resource_id=l, required_capacity=params_system["t_gkal"][g][k][a][l]))      
    return activity_resources

def create_TreatmentBounds(params_system: dict) -> list:
    treatment_bounds = []
    for g in params_system["G"]:
        treatment_bounds.append(TreatmentBounds(group_id=g, min_treatment_bound=params_system["Under_q_g"][g], max_treatment_bound=params_system["Over_q_g"][g]))      
    return treatment_bounds

def create_QualityBounds(params_system: dict) -> list:
    quality_bounds = []
    for g in params_system["G"]:
        for u in params_system["U_idx"][g]:
            quality_bounds.append(QualityBounds(group_id=g, quality_id=u, min_quality_bound=params_system["Under_q_gu"][g][u], max_quality_bound=params_system["Over_q_gu"][g][u]))      
    return quality_bounds


def convert_dm_from_json(params_system: dict, session: Session):
    """Retrieve Patients, Regions, Resources, Pathways, Activities, Facilities and Instances from json"""

    if params_system is None: params_system = {}
    list_patients = create_Patients_from_json(params_system)
    list_regions = create_Regions_from_json(params_system)
    list_resources = create_Resources_from_json(params_system)
    list_pathways = create_Pathways_from_json(params_system)
    list_facilities = create_Facilities_from_json(params_system)
    list_activities = create_Activities_from_json(params_system)
    instance = create_Instance_from_json( params_system)

    list_facility_affinities = create_FacilityAffinity(params_system)
    list_facility_resources = create_FacilityResources(params_system)
    list_facility_pathways = create_FacilityPathways(params_system)
    list_linked_facilities = create_LinkedFacilities(params_system)
    list_activity_resources = create_ActivityResources(params_system)
    list_case_mix_ratios = create_CaseMixRatios(params_system)
    list_treatment_bounds = create_TreatmentBounds(params_system)
    list_quality_bounds = create_QualityBounds(params_system)

    session.add_all(list_regions +  list_resources + list_patients + list_pathways + list_activities)
    session.flush()
    session.add_all(list_facilities)
    session.add_all(list_case_mix_ratios + list_facility_affinities + list_facility_resources + list_facility_pathways + list_linked_facilities +
                    list_activity_resources +  list_treatment_bounds + list_quality_bounds + [instance])
    return session