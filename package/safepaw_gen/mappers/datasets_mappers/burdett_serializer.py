import pandas as pd
from ...data_models.input_models import Facility, Region, Instance, Resource, PatientsGroup, Activity, Pathway
from .burdett_utils import get_ActivityResources, get_FacilityAffinity, get_FacilityResources, get_LinkedFacilities,\
get_CaseMixRatios, get_TreatmentBounds, get_QualityBounds, get_FacilityPathways, _get_df_resources
from .burdett_utils import hospitals, _get_df_pathways
from .burdett_utils import _define_grammar, _remove_trailing_comments, TreeToJSON
from lark import UnexpectedCharacters
import typer

def _get_facility_name(fid: str) -> str:
    return hospitals[fid.split("_")[0]]["name"]

def _get_facility_coordinates(fid: str) -> str:
    return hospitals[fid.split("_")[0]]["lat"], hospitals[fid.split("_")[0]]["lon"]


def _get_transferable(activity_name: str, activities_dict:dict) -> str:
    """Returns the group ID associated with pathway ID: pid"""
    transferable = next(v["transferable"] for v in activities_dict.values() if v["name"] == activity_name)
    return transferable

def _get_transfer_to(activity_name: str, activities_dict:dict) -> str:
    """Returns the group ID associated with pathway ID: pid"""
    transfer_to = next(v["transfer_to"] for v in activities_dict.values() if v["name"] == activity_name)
    return transfer_to



def get_Regions() -> list[Region]:
    """Creates Region instance"""
    list_regions = [Region(id="qld",
                            lbl="Queensland",
                            lat="-27.4698",
                            lon="153.0251",
                            dep_code="QLD")]
    return list_regions


def get_Facilities(data: dict) -> list[Facility]:
    """Creates Facility objects corresponding to unique wards"""
    list_facilities = []

    wards = [h for inner in data["WH"] for h in inner]
    for fid in wards:
        list_facilities.append(Facility(
                id = fid ,
                name = _get_facility_name(fid) ,
                region_id = "qld" ,
                lat =  _get_facility_coordinates(fid)[0], 
                lon = _get_facility_coordinates(fid)[1],
                facility_type = fid.split("_")[1]))

    return list_facilities



def get_Instance() -> Instance:
    """Returns object to store optimization instance parameters. Most variables are stores in a global config.yaml file """
   
    return Instance(
            id= "burdett",
            total_demand = 1.0,
            dep_code="QLD",
            perc_transfers = 1.0,
            alpha = 0,
            global_multiplier_demand= 1.0,
            global_multiplier_capacity= 1.0,
            global_perc_transfers= 1.0
        )


def get_Resources() -> list[Resource]:
    """Creates Resource object with id for unique """
    resources = ["OT", "ICU", "Ward"]
    return [Resource(id="cap_"+r, transfer_unit=1.0) for r in resources]



def get_PatientGroups(data: dict) -> list[PatientsGroup]:
    """Creates PatientGroups """
    list_patientsGroups = []
    for gid in data["G"]:
        list_patientsGroups.append(PatientsGroup(id=gid, lbl=gid))
    return list_patientsGroups


def get_Activities(df_pathways : pd.DataFrame) -> list[Activity]:
    """ get activities """
    activities = {1: {"name":"OT" , "transferable": True, "transfer_to":"ICU"},
                  2: {"name": "ICU", "transferable": True, "transfer_to":"Ward"},
                  3: {"name": "Ward", "transferable": False, "transfer_to":""}}
    
    df_pathways["pathway_activity"] = df_pathways["resource_id"].map(activities).str["name"]
    df_activities = df_pathways[["pathway_id", "patient_group_id", "resource_id", "resource_consumption", "pathway_activity"]].drop_duplicates()

    list_activities = []
    for _, row in df_activities.iterrows():
        list_activities.append(
            Activity(id= row["pathway_activity"], pathway_id=row["pathway_id"],
                        group_id =row["patient_group_id"], transferable=_get_transferable(row["pathway_activity"], activities),
                        transfer_to= _get_transfer_to(row["pathway_activity"], activities))
        )
    return list_activities


def get_PatientPathways(df_pathways : pd.DataFrame) -> list[Pathway]:
    """ get patients pathways"""    
    list_pathways = []
    for _, row in df_pathways[["pathway_id", "patient_group_id", "pathway_idx"]].drop_duplicates().iterrows():   
        list_pathways.append(Pathway(id= str(row["pathway_id"]),
                                  group_id = str(row["patient_group_id"]),
                                  quality_level = str(row["pathway_idx"]),
                                  group_benefit = 1))
    return list_pathways



def read_burdett():
    from importlib.resources import files

    filename= files("safepaw_gen") / "data" / "raw_data/data_burdett.txt"

    with open(filename, "r") as fp:
        data = fp.read()
    data = _remove_trailing_comments(data)
    burdett_parser = _define_grammar()
    try:
        tree = burdett_parser.parse(data)
    except UnexpectedCharacters as e:
        print("Error at line:", e.line)

    data_json = TreeToJSON().transform(tree)

    return data_json

def serialize_burdett(
        perc_allowed: float = typer.Option(0, help="Maximum allowed resources out percentage"),
        save_params: bool = typer.Option(True))-> dict:
    return serialize_burdett_core(perc_allowed, save_params)


def serialize_burdett_core(
        perc_allowed: float = 0,
        save_params: bool = True) -> dict:
    import json, os
    from ...data_models.input_models import FacilityAffinity
    from ...mappers.input_mappers import convert_dm_to_json
    from sqlmodel import Session, create_engine,  SQLModel

    data = read_burdett()

    DATABASE_URL = "sqlite://"
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)

    df_pathways  = _get_df_pathways(data)
    df_resources = _get_df_resources(data)
    with Session(engine) as session:

        list_regions = get_Regions()
        list_pathways = get_PatientPathways(df_pathways)
        list_facilities = get_Facilities(data)
        list_resources = get_Resources()
        list_patients =  get_PatientGroups(data)
        list_activities = get_Activities(df_pathways)
        instance = get_Instance()

        list_facility_affinities_rows = get_FacilityAffinity(list_facilities)
        list_facility_resources = get_FacilityResources(list_facilities, list_resources, df_resources, perc_allowed)
        list_facility_pathways = get_FacilityPathways(list_facilities, df_pathways)
        list_linked_facilities = get_LinkedFacilities(list_facilities)
        list_activity_resources = get_ActivityResources(df_pathways)
        list_case_mix_ratios = get_CaseMixRatios(data, df_pathways)
        list_treatment_bounds = get_TreatmentBounds(list_patients, data)
        list_quality_bounds = get_QualityBounds(data, df_pathways)
        
        session.add_all([instance] + list_regions + list_facilities + list_resources + list_patients + list_pathways + list_activities  +
                         list_facility_resources + list_facility_pathways + list_linked_facilities + list_activity_resources + list_case_mix_ratios + 
                         list_treatment_bounds + list_quality_bounds)

        session.bulk_insert_mappings(FacilityAffinity, list_facility_affinities_rows)
        session.flush()
        params_system  = convert_dm_to_json(session)
        if save_params:
            os.makedirs("outputs", exist_ok=True)
            with open("outputs/params_burdett.json", "w") as fp:
                json.dump(params_system, fp)
    return params_system


if __name__ == "__main__":
     import pyproj
     pyproj.datadir.set_data_dir(pyproj.datadir.get_data_dir())
     typer.run(serialize_burdett)