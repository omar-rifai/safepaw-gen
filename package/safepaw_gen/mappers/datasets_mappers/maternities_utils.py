import pandas as pd
from ...data_models.input_models import FacilityResources, FacilityPathways, LinkedFacilities, ActivityResources,\
    CaseMixRatios, TreatmentBounds, QualityBounds
from importlib.resources import files


root_opendata = files("safepaw_gen") / "data" / "open_data" 
root_deriveddata = files("safepaw_gen") / "data" / "derived_data" 

def  get_FacilityAffinity(df_instance: pd.DataFrame, df_geo_comms: pd.DataFrame, dep_code: str,
                           osrm_distances_file= root_deriveddata / "distances_maternities.parquet"):
    from shapely.geometry import Point
    from shapely import distance
    import geopandas as gpd
    import numpy as np
    
    if dep_code:
        df_distances = pd.read_parquet(osrm_distances_file)
        df_distances = df_distances[df_distances["dep_code"] == dep_code]
        distances = df_distances.pivot(values="distance", index="nofinesset", columns="region").to_numpy()
        print("Using OSRM distance succesfully")
    else:    
        print(f"No department selected fallback to geodesic distance") 
        distances = np.zeros((len(df_instance), len(df_geo_comms)))
        facilities_points = gpd.GeoSeries([Point(c) for c in df_instance["coords"]], crs="EPSG:4326").to_crs(df_geo_comms.crs)
        facility_geoms = np.asarray(facilities_points.values)
        region_geoms = np.asarray(df_geo_comms.geometry.values)
        distances = distance(facility_geoms[:, None], region_geoms[None,:])

    scores = 1 / np.where(distances == 0, 100, distances)
    facility_ids = df_instance["nofinesset"].to_numpy()
    region_ids = df_geo_comms["code"].to_numpy()

    rows = [{"facility_id": facility_ids[i], "region_id": region_ids[j], "affinity_score": float(scores[i, j]),}
    for i in range(len(facility_ids))
    for j in range(len(region_ids))]

    return rows



def get_FacilityResources(df_instance: pd.DataFrame, max_transferable_in : int = 0, max_transferable_out : int = 0, RESOURCE_ID="bed/days"):
   return [FacilityResources(
        facility_id = str(row['nofinesset']),
        resource_id = RESOURCE_ID,
        capacity = int(row['beds'] * 365),
        max_transferable_in = max_transferable_in,
        max_transferable_out = max_transferable_out
    ) for _, row in df_instance.iterrows()]



def get_FacilityPathways(list_facilities):
    pathways_dict = {"1": ["p1"], "2a": ["p1", "p2a"], "2b" :["p1", "p2a", "p2b"], "3": ["p1", "p2a", "p2b", "p3"]}
    return [FacilityPathways(facility_id=f.id, group_id=f.facility_type, pathway_id=p) for f in list_facilities for p in pathways_dict[f.facility_type]]


def get_LinkedFacilities(list_facilities):
    return [LinkedFacilities(facility_id=f.id, linked_facility_id=lf.id) for f in list_facilities for lf in list_facilities if f.id != lf.id]

def get_ActivityResources():
    from ...utils.data_utils import read_configs
    config = read_configs("data_maternity")
    required_resources={"bed/days":config["avg_length_of_stay"]}
    return [ActivityResources(activity_id="accouchement_"+g, pathway_id= "p"+g, group_id=g, resource_id=r, required_capacity=cap) for g in ["1", "2a", "2b", "3"]
            for r, cap in required_resources.items()]



def get_CaseMixRatios(df_instance: pd.DataFrame):
    """Returns the lower bound on patients asssigments per patient group, per commune"""
    from ...mappers.datasets_mappers.maternities_serializer import DF_LABOURS_ALL
    from ...utils.data_utils import read_configs

    config = read_configs("data_maternity")
    labour_types_distribution =  config["labour_types_distribution"]
    df_labours = DF_LABOURS_ALL[DF_LABOURS_ALL["dep_code"].isin(df_instance.apply(lambda x: x["dep_code"], axis=1))]
    df_labours = df_labours.drop(columns=["region_code"])
    df_comm_avg = (df_labours
        .groupby(["comm_code"], as_index=False)
        .agg(comm_deliveries=("deliveries_per_comm", "mean")))  
    
    d_gr = {}
    total_deliveries = df_comm_avg["comm_deliveries"].sum()
    for g, fraction in labour_types_distribution.items():
        d_gr[g] = { r: float((comm * fraction / total_deliveries))
                   for r, comm in zip(df_comm_avg["comm_code"], df_comm_avg["comm_deliveries"])}

    return [CaseMixRatios(group_id=g, region_id=r, ratio=ratio) for g, comm_ratios in d_gr.items() for r, ratio in comm_ratios.items()]

def get_TreatmentBounds(list_groups: list):
    from ...utils.data_utils import read_configs
    config = read_configs("data_maternity")    
    return [TreatmentBounds(group_id=g.id, min_treatment_bound=config["min_fraction_to_be_treated"] ,
                             max_treatment_bound=config["max_fraction_to_be_treated"]) for g in list_groups]


def get_QualityBounds(list_groups: list, list_qualities: list):
    from ...utils.data_utils import read_configs
    config = read_configs("data_maternity")    
    return [QualityBounds(group_id=g.id, quality_id=u, min_quality_bound=config["min_quality_bound"], max_quality_bound=config["max_quality_bound"]) 
            for g in list_groups for u in list_qualities]




def create_maternity_capacity_file():
    from pyproj import Transformer
    import pandas as pd 

    region_code_map = {'Auvergne-Rhône-Alpes': 84, "Provence-Alpes-Côte d'Azur": 93, 'Île-de-France': 11, 'Normandie': 28,
    'Occitanie': 76, 'Hauts-de-France': 32, 'Nouvelle-Aquitaine': 75, 'Grand Est': 44, 'Bretagne': 53, 'Centre-Val de Loire': 24,
    'Bourgogne-Franche-Comté': 27, 'Pays de la Loire': 52, 'Corse': 94
    }


    df_maternites = (
        pd.read_csv(root_opendata / "fichier_maternites_112021.csv", sep=";", low_memory=False)
            .rename(columns={"FI_ET": "nofinesset"})
    )
    
    
    df_finess_raw = pd.read_csv(root_opendata / "finess_etablissements.csv", sep=";", low_memory=False)
    t = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
    lon, lat = t.transform(df_finess_raw["coordxet"].values, df_finess_raw["coordyet"].values)
 
    df_finess = (
        df_finess_raw
            .loc[:,["nofinesset", "departement"]]
            .assign(department = lambda x :  x["departement"].astype(str).str.zfill(2),
                    coords=[(float(lon_), float(lat_)) for lon_, lat_ in zip(lon, lat)]
                   )
    )
    
    df_regions = pd.read_json("/data/departments-region.json")
    df_regions["num_dep"] = df_regions["num_dep"].astype(str)
    dep_map = df_regions.set_index("num_dep")["dep_name"].to_dict()
    reg_map = df_regions.set_index("num_dep")["region_name"].to_dict()
    
    
    
    df = (
        df_maternites
            .merge(df_finess, on="nofinesset", how="inner")
            .assign(region_name = lambda x : x["department"].map(reg_map),
                    dep_name = lambda x: x["department"].map(dep_map),
                   )
            .dropna(subset=["dep_name"])
    )

    df["region_code"] = df["region_name"].map(region_code_map)

    df = df.rename(columns = {"ANNEE": "year", "NOM_MAT": "facility_name", "TYPE": "type", "department": "dep_code",
                              "NOMCOM": "comm_name", "COM": "comm_code","ACCTOT":"deliveries_per_facility", "LIT_OBS": "beds"})\
        [["year", "nofinesset", "facility_name", "type", "region_code", "region_name","dep_code", "dep_name", "comm_code", "comm_name", "coords", "deliveries_per_facility", "beds"]]

    df["dep_code"] = df["dep_code"].astype(str)

    df.to_csv(root_deriveddata / "summary_maternity_capacity.csv")



def create_maternity_labours_file():
    import pandas as pd 

    df_labour_raw = pd.read_csv(root_opendata / "DS_ETAT_CIVIL_NAIS_COMMUNES_data.csv", sep=";", low_memory=False)
    df_communes_raw = pd.read_csv(root_opendata / "communes-france.csv", sep=";", low_memory=False)
    
    df_communes = df_communes_raw.rename(columns={"Année": "year", "Code Officiel Région": "region_code",\
                                "Code Officiel Département": "dep_code", "Code Officiel Commune": "comm_code"})
    
    
    df_communes["coordinates"] = df_communes["Geo Point"].apply(lambda v: (str(v).split(",")[0],  str(v).split(",")[1]))
    df_communes = df_communes[["region_code", "dep_code", "comm_code", "coordinates"]]
    df_communes.drop_duplicates()
    
    df_labour = df_labour_raw.loc[df_labour_raw["GEO_OBJECT"] == "COM"]
    df_labour = df_labour[["GEO","TIME_PERIOD", "OBS_VALUE"]].rename(columns={"GEO": "comm_code", "TIME_PERIOD": "year", "OBS_VALUE": "deliveries_per_comm"})
    df_labour = df_labour.merge(df_communes, on=["comm_code"], how="left")[["year", "comm_code","dep_code", "region_code", "coordinates", "deliveries_per_comm" ,]]
    df_labour[["comm_code", "dep_code", "region_code"]] = df_labour[["comm_code", "dep_code", "region_code"]].apply(lambda x: x.astype(str))

    df_labour.to_csv(root_deriveddata/ "summary_maternity_labours.csv")

    return 