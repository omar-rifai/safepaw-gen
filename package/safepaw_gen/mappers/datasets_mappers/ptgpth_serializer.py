import pandas as pd
import typer
import os
from ...data_models.input_models import Facility, Region, Instance, Resource, PatientsGroup, Activity, Pathway
from ...mappers.datasets_mappers.ptgpth_utils import load_data, get_geo_polygon, summarize_geo_data, get_pop65p,\
    get_finess_info, get_required_resources, get_transfer_to, get_transferable,\
    get_activities_per_group_pathway, list_resources_ids, getFacilityType
from importlib.resources import files

pathway_benefit = {"HC":1, "DOM":2, "HCHDJ": 1.25, "HDJ":1.5}

def get_Regions(gdf_summary: pd.DataFrame) -> list[Region]:
    """Creates Region instance (cantons) given a department code (cantons are grouped by bureau de vote)"""
    list_regions = [Region(id=row["can_code"],lon=row["geometry"].centroid.x, lat=row["geometry"].centroid.y)for _,row in  gdf_summary.iterrows()]
    return list_regions


def get_Facilities(df_mco : pd.DataFrame, df_ssr : pd.DataFrame,  df_finess:pd.DataFrame, dep_code: int) -> list[Facility]:
    """Creates Facility objects corresponding to unique nofinesset ids """
    from ...mappers.datasets_mappers.ptgpth_utils import get_facility_visits
    list_facilities = []
    gdf_cantons = get_geo_polygon()
    gdf_geo = summarize_geo_data(gdf_cantons, get_pop65p(), dep_code)
    
    if gdf_geo.empty:
        raise Exception(f"Geographic data unavailable for department code: {dep_code}.")
    
    for row in df_finess.itertuples():     
        list_facilities.append(Facility(
            id = row.nofinesset,
            facility_type = getFacilityType(row.nofinesset, df_mco, df_ssr),
            name = row.rs,
            region_id = row.can_code,
            lon = row.lon,
            lat = row.lat,
            nbr_visits= get_facility_visits(row.nofinesset, df_mco, df_ssr)))
    list_facilities = add_dom_facility(list_facilities,  gdf_geo)
    list_facilities = add_orth_facility(list_facilities,  gdf_geo)
    return list_facilities


def add_orth_facility(list_facilities: list[Facility], gdf_geo: pd.DataFrame) -> list[Facility]:
    """Append a virtual facility corresponding to patients' home"""
    from ...mappers.datasets_mappers.ptgpth_utils import get_default_geo_info
    default_can_code, default_coords = get_default_geo_info(gdf_geo)
    list_facilities.append(Facility(
            id = "ORTH",
            name = "Orthopedic Center",
            facility_type="Other",
            region_id =  default_can_code,
            lat =default_coords[1],
            lon =default_coords[0]))
    return list_facilities


def add_dom_facility(list_facilities: list[Facility],
                     gdf_geo: pd.DataFrame) -> list[Facility]:
    """Append a virtual facility corresponding to patients' home"""
    from ...mappers.datasets_mappers.ptgpth_utils import get_default_geo_info
    default_can_code, default_coords = get_default_geo_info(gdf_geo)
    
    list_facilities.append(Facility(
            id = "DOM",
            name = "Home Care",
            facility_type="Other",
            region_id = default_can_code,
            lat =default_coords[1], 
            lon = default_coords[0]))
    return list_facilities



def get_Instance(total_demand: float, p_transf: float, dep_code:str,
                global_multiplier_demand: float, global_multiplier_capacity: float, global_perc_transfers: float) -> Instance:
    """Returns object to store optimization instance parameters."""
    
    return Instance(
            id="pthptg",
            dep_code=dep_code,
            total_demand=total_demand,
            perc_transfers = p_transf,
            alpha = 0.0125,
            global_multiplier_demand = global_multiplier_demand,
            global_multiplier_capacity = global_multiplier_capacity,
            global_perc_transfers = global_perc_transfers, 
        )

def get_Resources(list_resources_ids: list) -> list[Resource]:
    """Creates Resource object with id for unique """
    return [Resource(id=l, transfer_unit=1) for l in list_resources_ids]


def get_PatientGroups(list_group_ids: list) -> list[PatientsGroup]:
    """Creates PatientGroups. All groups have all pathways"""
    list_patientsGroups = []
    for gid in list_group_ids:
        list_patientsGroups.append(PatientsGroup(id=gid))
    return list_patientsGroups


def get_Activities(A_idx: dict) -> list[Activity]:
    """ get activities """
    list_activities = []
    tranferable_activities = get_transferable(A_idx)
    transfer_to_activities = get_transfer_to(A_idx)
    for g in A_idx.keys():
        for k in A_idx[g].keys():
            for a in A_idx[g][k]:
                if a in transfer_to_activities[g][k]: 
                    transfer_to = transfer_to_activities[g][k][a]
                else: transfer_to = ""
                list_activities.append(
                    Activity(id= a, pathway_id=k, group_id=g, transferable=a in tranferable_activities[g][k],
                        transfer_to= transfer_to))
    return list_activities


def get_PatientPathways(list_pathways_ids: list, list_groups: list, pathway_benefit:dict, quality_levels:dict) -> list[Pathway]:
    """ get patients pathways"""
    list_pathways = [] 
    for g in list_groups:                      
        list_pathways.extend([Pathway(id=p_id, group_id = g, quality_level = quality_levels[p_id],
                            group_benefit = pathway_benefit[p_id]) for p_id in list_pathways_ids])
    return list_pathways

def get_data(dep_code: str):
    """prepare the raw data in DataFrames."""
    from ...mappers.datasets_mappers.ptgpth_utils import verify_department_finess
    df_types_parcours, df_mco, df_ssr = load_data(dep_code)
    df_types_parcours = df_types_parcours.groupby(["sej_type", "type_parcours", "SSR_TYPE"], as_index=False)["nb"].sum()
    df_types_parcours = df_types_parcours[df_types_parcours["nb"].fillna(0) >= 3]
    gdf_geo =  get_geo_polygon()
    gdf_summary = summarize_geo_data(gdf_geo, get_pop65p(), dep_code)
    df_finess = get_finess_info(df_mco, df_ssr, gdf_geo)
    df_mco, df_ssr = verify_department_finess(df_mco, df_ssr, df_finess)
    return df_types_parcours, df_mco, df_ssr, gdf_summary, df_finess


def serialize_ptgpth(
        dep_code: str = typer.Option("42", help="department code"),
        p_transf: float = typer.Option(1, help="Maximum allowed patients transfer percentage"),
        p_orth:float = typer.Option(0, help="Orthopedic center percentage additional resources"),
        resources_mult: float = typer.Option(1, help="Multiplier for the available resources"),
        quality_requirement: bool = typer.Option(False, help="Impose a strict distribution of patients to pathways as described in article."),
        global_multiplier_demand = typer.Option(1.0, help="Global multiplier for the instance demand"),
        global_multiplier_capacity = typer.Option(1.0, help="Global multiplier for the instance capacity"),
        global_perc_transfers = typer.Option(0.0, help=" Global percentage of allowed transfers "),
        save_params: bool = typer.Option(True)
        ):
    return serialize_ptgpth_core(dep_code, p_transf, p_orth, resources_mult, quality_requirement,
                                 global_multiplier_demand, global_multiplier_capacity, global_perc_transfers,
                                 save_params)


def serialize_ptgpth_core(
        dep_code: str = "42",
        p_transf: float = 1,
        p_orth:float = 0,
        resources_mult: float = 1,
        quality_requirement: bool = False,
        global_multiplier_demand: float = 1.0,
        global_multiplier_capacity: float = 1.0,
        global_perc_transfers: float = 0.0,
        save_params: bool = True):
    
    """Serialize PTG PTH Data and write to file
     Parameters
     -----------
        p_transf: allowed transfers percentage for patients
        resources_mult: applies a multiplier factor to the resources on generation
        
        global_multiplier_capacity: Saves a multiplier factor for later use (does NOT have direct impact on data)
        global_perc_transfer: Saves a resources transfers percentage (does NOT have direct impact on data)
    """

    from ...mappers.input_mappers import convert_dm_to_json
    from ...mappers.datasets_mappers.ptgpth_utils import get_ActivityResources, get_FacilityAffinity,\
    get_FacilityResources, get_FacilityPathways, get_LinkedFacilities, get_CaseMixRatios, get_TreatmentBounds, get_QualityBounds
    import json
    from sqlmodel import Session, SQLModel, create_engine
 
    if quality_requirement: quality_levels = {"DOM":"1","HC":"3","HDJ":"2","HCHDJ":"2"}
    else: quality_levels = {"DOM":"0","HC":"0","HDJ":"0","HCHDJ":"0"}

    df_types_parcours, df_mco, df_ssr, gdf_summary, df_finess = get_data(dep_code)
    list_patientGroups_ids = list(set(df_types_parcours['sej_type'] +  "_" + df_types_parcours['type_parcours'].str.replace(" + ", "_", regex=False)))

    list_pathways_ids =  list(df_types_parcours["SSR_TYPE"].unique())
    A_idx = get_activities_per_group_pathway(list_pathways_ids, list_patientGroups_ids)
    t_gkal = get_required_resources(A_idx, list_resources_ids)


    list_Regions = get_Regions(gdf_summary)
    list_Resources = get_Resources(list_resources_ids)
    list_PatientsGroups = get_PatientGroups(list_patientGroups_ids)
    list_Activities = get_Activities(A_idx)
    list_Facilities = get_Facilities(df_mco, df_ssr, df_finess, dep_code)
    list_Pathways = get_PatientPathways(list_pathways_ids, list_patientGroups_ids, pathway_benefit, quality_levels)
    instance = get_Instance(int(df_types_parcours["nb"].sum()), p_transf, dep_code,
                             global_multiplier_demand, global_multiplier_capacity, global_perc_transfers)

    list_facility_resources = get_FacilityResources(t_gkal, list_resources_ids, df_mco, df_ssr, df_finess, df_types_parcours,
                                                    p_orth, resources_mult)
    list_facility_affinities = get_FacilityAffinity(list_Facilities, gdf_summary)
    
    list_facility_pathways = get_FacilityPathways(list_facility_resources, list_Facilities, t_gkal, A_idx)
    list_linked_facilities = get_LinkedFacilities(list_Facilities)
    list_activity_resources = get_ActivityResources(t_gkal,  A_idx)
    list_case_mix_ratios = get_CaseMixRatios(gdf_summary, df_types_parcours)
    list_treatment_bounds = get_TreatmentBounds(list_PatientsGroups)
    list_quality_bounds = get_QualityBounds(quality_levels, list_patientGroups_ids)

    DATABASE_URL = "sqlite://"
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([instance] + list_Regions + list_Facilities + list_Resources + list_PatientsGroups + list_Pathways + list_Activities +
                         list_facility_affinities + list_facility_resources + list_facility_pathways + list_linked_facilities + list_activity_resources +
                         list_case_mix_ratios + list_treatment_bounds + list_quality_bounds)

        session.flush()
        params_system = convert_dm_to_json(session)
    
    if save_params:
        os.makedirs("outputs", exist_ok=True)
        with open("outputs/params_ptgpth.json", "w") as fp:
            json.dump(params_system, fp)

    return params_system    



if __name__ == "__main__":
     import pyproj
     pyproj.datadir.set_data_dir(pyproj.datadir.get_data_dir())
     typer.run(serialize_ptgpth)