from pathlib import Path
from importlib.resources import files


root_path = files("safepaw_gen")

def read_inputs(file_params_system):
    import json
    with open(file_params_system, "r") as f:
        params_system = json.load(f)

    return params_system


def get_pathways_usage(params_system: dict, P_gk: dict) -> dict:
    """Returns the percentage of patients for each pathway"""
    n_total = sum(params_system["D"] * P_gk[(g, k)] for g in params_system["G"]
                                                       for k in params_system["K_idx"][g])
    all_pathways = list({k for g in params_system["G"] for k in params_system["K_idx"][g]})
    utilisation = {k: 0 for k in all_pathways}
    for k in all_pathways:
        n_k = 0
        for g in params_system["G"]:
            if k in params_system["K_idx"][g]:
                n_k += params_system["D"] * P_gk[(g, k)] 
        utilisation[k] = round(n_k / n_total,3) if n_total != 0 else 0
    return utilisation



def read_metadata(inputfile : str | Path):
    """
    Reads metadata from a JSON file.
    """
    import json

    with open(inputfile, "r") as f:
        metadata = json.load(f)

    return metadata


def read_configs(config_category, config_path=root_path /"config.yaml"):
    import yaml

    with open(config_path, "r") as f:
        configs = yaml.safe_load(f)

    return configs.get(config_category)



def read_geojson_projected(filename: str | Path):
    import geopandas as gpd
    gdf = gpd.read_file(Path(filename))
    if gdf.empty:
        raise ValueError(f"GeoJSON file {filename} contains no features.")
    gdf = gdf.to_crs(epsg = 2154)
    return gdf

    

def get_distance_to_dep(dep_name : str, coords: list) -> int:
    """ Returns the distance in kms between a french departments and a point [lon, lat]"""
    from shapely.geometry import Point
    import geopandas as gpd

    geo_deps = read_geojson_projected("/data/departements.geojson")
    try:
        dep_geo = geo_deps.loc[geo_deps["nom"] == dep_name, "geometry"].iloc[0]
    
    except IndexError:
        raise ValueError(f"Departments {dep_name} not found")

    gdf_point = gpd.GeoSeries(Point(coords), crs="EPSG:4326").to_crs(geo_deps.crs)
        
    distance_m = gdf_point.iloc[0].distance(dep_geo)
    distance_km = distance_m / 1000
    
    return distance_km

def get_department_coords(dep_name: str, dep_centroids):
    return dep_centroids[dep_name]

