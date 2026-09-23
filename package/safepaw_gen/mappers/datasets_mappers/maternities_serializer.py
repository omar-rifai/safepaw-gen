import pandas as pd
from typing import Union
from ...data_models.input_models import Facility, Region, Instance, Resource, PatientsGroup, Activity, Pathway
import geopandas as gpd
import numpy as np
import typer
from importlib.resources import files


root_opendata = files("safepaw_gen") / "data" / "open_data" 
root_deriveddata = files("safepaw_gen") / "data" / "derived_data" 

FACILITY_TYPES = ["1", "2a", "2b", "3"]
RESOURCE_ID = "bed/days"
DF_LABOURS_ALL = pd.read_csv(root_deriveddata / "summary_maternity_labours.csv", low_memory=False)
DF_GEO_COMMS = gpd.read_parquet(root_opendata / "communes-50m.parquet")
DF_GEO_COMMS_METERS= DF_GEO_COMMS.to_crs(epsg=2154)
centroids_m = DF_GEO_COMMS_METERS.geometry.centroid
centroids_wgs84 = centroids_m.to_crs(epsg=4326)
DICT_COMM_CENTROIDS = dict(zip(
    DF_GEO_COMMS["code"],
    np.vstack([centroids_wgs84.x.values,
               centroids_wgs84.y.values]).T
))


def pad_single(dep_code: str):
    if not dep_code.isdigit():
       return dep_code
    if int(dep_code) < 10 and len(dep_code) == 1:
        return "0" + dep_code
    return dep_code


def get_Regions(df_instance: pd.DataFrame) -> list[Region]:
    """Creates `Region` instance using public data on French communes (Commune code and coordinates)"""
    df_labours = DF_LABOURS_ALL[DF_LABOURS_ALL["dep_code"].isin(df_instance.apply(lambda x: x["dep_code"], axis=1))]
    df_geo_comms = DF_GEO_COMMS_METERS[DF_GEO_COMMS_METERS["code"].isin(df_labours["comm_code"])]
    list_regions = []
    for _, row in df_geo_comms.iterrows():
        list_regions.append(Region(id=row["code"],
                                   lbl=row["nom"],
                                   lon=DICT_COMM_CENTROIDS[row["code"]][0],
                                   lat=DICT_COMM_CENTROIDS[row["code"]][1],
                                   dep_code=row["departement"],
                                   comm_code=row["code"]
                                   ))
    
    return list_regions


def get_Facilities(df_instance: pd.DataFrame) -> list[Facility]:
    """
    Creates Facility objects corresponding to unique nofinesset ids with (bed/days) as resource 
    and availiable pathways dependent on to the facility type (1,2a,2b,3). We average the number of deliveries
    per facility across the year sand take the latest number of beds recorded
    """
    def row_to_facility(row):
        return Facility(
            id = str(row['nofinesset']),
            name = str(row['facility_name']),
            facility_type = str(row["type"]),
            region_id = row['comm_code'],
            lon = row['coords'][0],
            lat = row['coords'][1],
            nbr_visits= row["deliveries_per_facility"])
    
    list_facilities = df_instance.apply(row_to_facility, axis=1).tolist()
    return list_facilities




def get_Instance(df_instance:dict, region_code: str, dep_code:str,
                 global_multiplier_demand:float = 1.0,
                 global_multiplier_capacity: float = 1.0,
                 global_perc_transfers: float = 0.0) -> Instance:
    """Returns object to store optimization instance parameters"""
    from ...utils.data_utils import read_configs
    config = read_configs("data_maternity")    
    return Instance(id = "maternities",
            region_code = region_code,
            dep_code = dep_code,
            total_demand =int(df_instance["deliveries_per_facility"].sum()),
            perc_transfers = 0, # patient transfers
            alpha = config["alpha"],
            global_multiplier_demand = global_multiplier_demand,
            global_multiplier_capacity = global_multiplier_capacity,
            global_perc_transfers = global_perc_transfers, # global resources transfers
        )



def get_Resources(list_resources: list) -> list[Resource]:
    """Creates Resource object with id for unique resource (bed/days)"""
    from ...utils.data_utils import read_configs
    from ...data_models.input_models import Resource
    config = read_configs("data_maternity")
    return [Resource(id=x,transfer_unit=config["resource_transfer_unit"]) for x in list_resources]


def get_PatientsGroups(groups_ids: list) -> list[PatientsGroup]:
    """Creates PatientGroups corresponding to French labour types status codes (1,2a,2b,3)"""
    list_patientsGroups = []
    for gid in groups_ids:
        list_patientsGroups.append(PatientsGroup(id= gid,lbl=gid))
    return list_patientsGroups


def get_Activities(groups_ids: list) -> list[Activity]:
    """Creates Activity objects
    Required resources is the average length of stay for a labour in France in bed/days"""
    from ...data_models.input_models import Activity    
    list_activities = [Activity(id="accouchement_"+g, pathway_id="p"+g, group_id=g, transferable=False, transfer_to=None)for g in groups_ids]
    return list_activities


def get_PatientPathways(groups_ids: list) -> list[Pathway]:
    """Creates Pathways objects for each patientGroup type"""
    pathways = [Pathway(id= "p"+g, group_id = g, quality_level = "0",
                         group_benefit = 1) for g in groups_ids]
    return pathways

    


def serialize_maternity_core(df_instance:dict, region_code:str, dep_code:str,
                            global_multiplier_demand, global_multiplier_capacity, global_perc_transfers,
                            save_params: bool = False,
                             ) -> Union[dict, dict]:
    """Serialize maternite objects into dictionaries (params_system.json; params_metadata.json)"""
    import json, os
    from ...data_models.input_models import FacilityAffinity
    from ...mappers.input_mappers import convert_dm_to_json
    from ...mappers.datasets_mappers.maternities_utils import  get_FacilityAffinity, get_FacilityResources, get_FacilityPathways, get_LinkedFacilities,\
    get_ActivityResources, get_CaseMixRatios, get_TreatmentBounds, get_QualityBounds
    from sqlmodel import Session, create_engine,  SQLModel

    df_communes = DF_GEO_COMMS_METERS
    if region_code:
        df_communes = df_communes[df_communes["region"]==region_code]
    if dep_code:
        df_communes = df_communes[df_communes["departement"]==dep_code]


    DATABASE_URL = "sqlite://"
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:

        list_regions = get_Regions(df_instance)
        list_facilities = get_Facilities(df_instance)
        list_resources = get_Resources([RESOURCE_ID])
        list_patients = get_PatientsGroups(FACILITY_TYPES)
        list_pathways = get_PatientPathways(FACILITY_TYPES)
        list_activities = get_Activities(FACILITY_TYPES)
        instance = get_Instance(df_instance, region_code, dep_code,
                                global_multiplier_demand=global_multiplier_demand,
                                global_multiplier_capacity=global_multiplier_capacity,
                                global_perc_transfers=global_perc_transfers)
        
        list_qualities = list(set([k.quality_level for k in list_pathways]))
        list_facility_affinities_rows = get_FacilityAffinity(df_instance, df_communes, dep_code)
        list_facility_resources = get_FacilityResources(df_instance, max_transferable_in=0, max_transferable_out=0, RESOURCE_ID=RESOURCE_ID)
        list_facility_pathways = get_FacilityPathways(list_facilities)
        list_linked_facilities = get_LinkedFacilities(list_facilities)
        list_activity_resources = get_ActivityResources()
        list_case_mix_ratios = get_CaseMixRatios(df_instance)
        list_treatment_bounds = get_TreatmentBounds(list_patients)
        list_quality_bounds = get_QualityBounds(list_patients, list_qualities)
        
        session.add_all([instance] + list_regions + list_facilities + list_resources + list_patients + list_pathways + list_activities  +
                         list_facility_resources + list_facility_pathways + list_linked_facilities + list_activity_resources + list_case_mix_ratios + 
                         list_treatment_bounds + list_quality_bounds)

        session.bulk_insert_mappings(FacilityAffinity, list_facility_affinities_rows)
        session.flush()
        params_system  = convert_dm_to_json(session)
    
    if save_params :
        os.makedirs("outputs", exist_ok=True)
        with open("outputs/params_maternity.json", "w") as fp:
            return json.dump(params_system, fp)
    return params_system



def serialize_maternities(
        region_code: str = typer.Option(None, help="French region code (as string)"),
        dep_code: str = typer.Option(None, help="French department code (as string)"),
        save_params: bool = typer.Option(True),
        global_multiplier_demand = typer.Option(1.0, help="Global multiplier for the instance demand"),
        global_multiplier_capacity = typer.Option(1.0, help="Global multiplier for the instance capacity"),
        global_perc_transfers = typer.Option(0.0, help=" Global percentage of allowed transfers"),
        ):
    
    import ast
    df_instance = pd.read_csv(root_deriveddata / "summary_maternity_capacity.csv")
    df_instance.loc[df_instance["comm_code"] == "85166", "comm_code"] = "85194"
   
    df_instance["coords"] = df_instance["coords"].apply(ast.literal_eval) # update the commune code of Olonne-sur-Mer
    df_instance.sort_values(by=["year"], ascending=False, inplace=True)
    if region_code: 
        df_instance = df_instance[df_instance["region_code"].astype(str) == str(region_code)]
    if dep_code: df_instance = df_instance[df_instance["dep_code"] == pad_single(dep_code)]
    df_instance = df_instance[df_instance["year"]==2023]
    df_instance = df_instance.drop_duplicates(subset=["nofinesset"], keep="first")

    return serialize_maternity_core(df_instance, region_code, dep_code,
                                    global_multiplier_demand, global_multiplier_capacity, global_perc_transfers,
                                    save_params)


if __name__ == "__main__":
     typer.run(serialize_maternities)