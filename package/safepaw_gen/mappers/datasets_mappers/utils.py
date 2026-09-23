
import pandas as pd
import geopandas as gpd
import ast
from importlib.resources import files

root_opendata = files("safepaw_gen") / "data" / "open_data"
root_deriveddata = files("safepaw_gen") / "data" / "derived_data"


DF_GEO_COMMS = gpd.read_parquet(root_opendata / "communes-50m.parquet")
DF_GEO_COMMS_METERS= DF_GEO_COMMS.to_crs(epsg=2154)
centroids_m = DF_GEO_COMMS_METERS.geometry.centroid
centroids_wgs84 = centroids_m.to_crs(epsg=4326)



def osrm_distance_matrix(df_facilities, df_regions, chunk_size = 50):
    import requests
    import numpy as np
    """
    Calculate the distance matrix between facilities and regions using OSRM API.
    """
    distances = []
    url = "http://router.project-osrm.org/table/v1/driving/"

    fcoords = df_facilities["coords"].to_list()
    rcoords = df_regions["coords"].to_list()
    n_facilities = len(fcoords)

    for chunk in range(0, len(rcoords), chunk_size):

        rcoords_chunk = rcoords[chunk:chunk+chunk_size]
        n_coords = len(fcoords) + len(rcoords_chunk)

        coords = ";".join([f"{lon},{lat}" for lon, lat in fcoords + rcoords_chunk])

        r = requests.get(url + coords, params={"annotations": "distance", 
                                            "sources":";".join(map(str, range(n_facilities))),
                                            "destinations":";".join(map(str, range(n_facilities, n_coords))) })
        if r.status_code != 200:
            raise Exception(f"OSRM request failed with status code {r.status_code}")
        distances.append(np.asarray(r.json()["distances"], dtype=np.float32))
    return np.hstack(distances)



def convert_to_df(distances:np.array, dep_code, list_finess, list_regions):
    
    df_distances = pd.DataFrame(columns=["dep_code", "nofinesset", "region", "distance"])
    for i, data_i in enumerate(distances):
        
        df_temp = pd.DataFrame({
            "dep_code": dep_code,
            "nofinesset": list_finess[i],
            "region": list_regions,
            "distance": data_i,
        })
       
        df_distances = pd.concat([df_distances, df_temp], ignore_index=True)
    return df_distances


def pad_single(dep_code: str):
    if not dep_code.isdigit():
       return dep_code
    if int(dep_code) < 10 and len(dep_code) == 1:
        return "0" + dep_code
    return dep_code


def get_instance_maternities(dep_code: str = None):
    df_instance = pd.read_csv(root_deriveddata / "summary_maternity_capacity.csv")
    df_instance.loc[df_instance["comm_code"] == "85166", "comm_code"] = "85194"

    df_instance["coords"] = df_instance["coords"].apply(ast.literal_eval) # update the commune code of Olonne-sur-Mer
    df_instance.sort_values(by=["year"], ascending=False, inplace=True)

    if dep_code: df_instance = df_instance[df_instance["dep_code"] == pad_single(dep_code)]
    df_instance = (df_instance.groupby(
        ["nofinesset","region_code", "region_name", "type", "dep_code",
            "dep_name", "comm_code", "facility_name", "comm_name", "coords"],
        as_index=False)
    .agg(deliveries_per_facility=("deliveries_per_facility", "mean"),
        beds=("beds", "first")))
    df_instance = df_instance.drop_duplicates(subset=["nofinesset"], keep="first")
    return df_instance[["nofinesset", "dep_code", "coords"]]


def get_regions_maternities(dep_code: str):
    df_communes = DF_GEO_COMMS_METERS[DF_GEO_COMMS_METERS["departement"].isin([pad_single(dep_code)])].copy()
    df_communes["coords"] = centroids_wgs84.apply(lambda x: (x.x, x.y))
    df_communes =df_communes[["code","nom", "coords"]]
    return df_communes



def get_instance_pthptg(dep_code: str = None):
    from ...mappers.datasets_mappers.ptgpth_utils import get_geo_polygon, get_finess_info, load_data
    _, df_mco, df_ssr = load_data(dep_code)
    gdf_geo =  get_geo_polygon()
    df_finess = get_finess_info(df_mco, df_ssr, gdf_geo)
    df_finess["coords"] = df_finess.apply(lambda x: (x["lon"], x["lat"]),axis=1)
    df_finess = df_finess[["nofinesset", "can_code", "coords"]]
    return df_finess

def get_regions_pthptg(dep_code: str = None):
    from ...mappers.datasets_mappers.ptgpth_utils import get_geo_polygon
    gdf_cantons = get_geo_polygon()
    df_cantons = gdf_cantons[gdf_cantons["dep_code"] == dep_code].copy()
    df_cantons["coords"] = df_cantons["geometry"].to_crs(epsg=2154).centroid.to_crs(epsg=4326).apply(lambda x: (x.x, x.y))
    df_cantons = df_cantons[["can_code", "dep_code","coords"]].rename(columns={"can_code":"code"})
    return df_cantons 

def save_distances_matrix(instance_type: str = "maternities"):
    df_deps = pd.read_csv(root_opendata / "departements-france.csv")
    list_deps = list(df_deps["code_departement"].unique())
    df_all = pd.DataFrame()
    for dep_code in list_deps:
        try:
            if instance_type == "maternities":
                df_instance = get_instance_maternities(dep_code)
                df_regions = get_regions_maternities(dep_code)
            elif instance_type == "pthptg": 
                df_instance = get_instance_pthptg(dep_code)
                df_regions = get_regions_pthptg(dep_code)
            print(f"Adding data for department {dep_code}")
            distances = osrm_distance_matrix(df_instance, df_regions)
            df_temp = convert_to_df(distances, dep_code, df_instance["nofinesset"].tolist(), df_regions["code"].tolist())
            df_all = pd.concat([df_all, df_temp], ignore_index=True)
        except Exception as e:
            print("failed with exception", e)
            continue
    df_all["dep_code"] = df_all["dep_code"].astype(str)
    df_all["nofinesset"] = df_all["nofinesset"].astype(str)
    df_all["region"] = df_all["region"].astype(str)
    df_all.to_parquet(f"{root_deriveddata} /distances_{instance_type}.parquet", index=False)