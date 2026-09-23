import pandas as pd
import geopandas as gpd
from typing import Tuple
from ...data_models.input_models import FacilityAffinity, FacilityResources, FacilityPathways, LinkedFacilities, ActivityResources,\
    CaseMixRatios, TreatmentBounds, QualityBounds
from ...data_models.input_models import Facility
from importlib.resources import files

root_opendata = files("safepaw_gen") / "data" / "open_data"
root_rawdata = files("safepaw_gen") / "data" / "raw_data"
root_deriveddata = files("safepaw_gen") / "data" / "derived_data"

nb_kine_preop = {"PTG":10, "PTH":15}
specialities = ["CSC", "DERMA", "ENDO", "GASTRO", "GYNECO", "OPH", "ORL", "RHUMA", "URO"]
list_resources_ids = ["CHIR/ORTHO", "ANES", "KINE_MCO", "DAY_HC", "KINE_DOM", "KINE_SSR", "finance"]
list_resources_ids.extend(specialities)

# number of resource units needed for each resource type -> groupprefix_pathway
post_op_scenarios = {"DAY_HC":{"PTG_HC":28,"PTH_HC":21,"PTG_DOM":0,"PTH_DOM":0,"PTG_HCHDJ":21,"PTH_HCHDJ":14,"PTG_HDJ":0,"PTH_HDJ":0},
                     "KINE_SSR":{"PTG_HC":0,"PTH_HC":0,"PTG_DOM":0,"PTH_DOM":0,"PTG_HCHDJ":20,"PTH_HCHDJ":15,"PTG_HDJ":25,"PTH_HDJ":20},
                     "KINE_DOM":{"PTG_HC":0,"PTH_HC":0,"PTG_DOM":25,"PTH_DOM":20,"PTG_HCHDJ":0,"PTH_HCHDJ":0,"PTG_HDJ":0,"PTH_HDJ":0}}

finance_costs= {"PTG": {"CHIR/ORTHO_pre":46, "ANES" : 46, "CSC": 34.75, "DERMA": 40,"ENDO": 40, "GASTRO": 40, "GYNECO": 40,
                  "OPH":40, "ORL":40, "RHUMA":40, "URO":40, "KINE_MCO": 9.95, "CHIR/ORTHO+ANES": 4365.61, "DAY_HC":769.56, "KINE_SSR":126.80,"KINE_DOM": 370.99, "CHIR/ORTHO_post":46},
          "PTH": {"CHIR/ORTHO_pre": 46, "ANES": 46, "CSC":34.75, "DERMA":40, "ENDO":40, "GASTRO":40, "GYNECO":40, "OPH":40,
                  "ORL": 40, "RHUMA":40, "URO":40, "KINE_MCO": 9.95, "CHIR/ORTHO+ANES": 3966.66, "DAY_HC":803.30, "KINE_SSR":127.63, "KINE_DOM":370.99, "CHIR/ORTHO_post":46}}

df_mco_flag_fields = {"CSC": "PCAR", "DERMA": "PDER", "RHUMA": "PRHU",
                           "GASTRO": "PGAS", "OPH": "POPH", "ENDO": "PEND", "GYNECO": "PTRUE",
                            "URO": "PTRUE", "ORL": "PTRUE"}


def rescale_costs(finance_costs: dict)-> dict:
    """Rescale the finance cost from euros to k euros for better numerical stability"""
    for g, gl in finance_costs.items():
        for a, cost in gl.items():
            finance_costs[g][a] = round(cost/1000,5)
    return finance_costs 

def get_FacilityAffinity(list_Facilities: list[Facility], gdf_summary: pd.DataFrame):
    list_finess = [x.id for x in list_Facilities]
    affinities = get_region_affinities(gdf_summary, list_Facilities)
    return [
        FacilityAffinity(facility_id= nofinesset,region_id= can_code, affinity_score = affinities[can_code][nofinesset]) 
            for nofinesset in list_finess for can_code in gdf_summary["can_code"]]


def get_FacilityResources(t_gkal: dict, list_resources_ids: list,df_mco : pd.DataFrame, df_ssr : pd.DataFrame,
                          df_finess:pd.DataFrame,  df_types_parcours: pd.DataFrame, p_orth, multiplier=1.0):
    list_finess = list(df_finess["nofinesset"].unique()) + ["DOM"]
    m_hl = get_resources_capacities(t_gkal, list_finess, df_types_parcours, df_ssr, df_mco, multiplier)
    
    max_transferable_in = {l: 0 if l != "finance" else 3 for l in list_resources_ids }
    max_transferable_out = {l: 0 if l != "finance" else 3 for l in list_resources_ids }
    list_facility_resources = [FacilityResources(facility_id=h, resource_id=l, capacity=m_hl[h][l],
                               max_transferable_in=max_transferable_in[l], max_transferable_out=max_transferable_out[l])
                            for h in m_hl.keys() for l in list_resources_ids]
    
    orth_resource_capacities = get_frac_resource_capacities(m_hl, p_orth)
    list_facility_resources.extend(FacilityResources(facility_id="ORTH", resource_id=l, capacity=orth_resource_capacities[l],
                                                     max_transferable_in=max_transferable_in[l], max_transferable_out=max_transferable_out[l]) for l in orth_resource_capacities)
    return list_facility_resources




def get_FacilityPathways(list_facility_resources, list_facilities, t_gkal, A_idx):
    
    pathway_resources = {g: {k: {r for a in A_idx[g][k] for r, amount in t_gkal[g][k][a].items() if amount > 0}for k in A_idx[g]} for g in A_idx}

    facility_resources = {}
    for fr in list_facility_resources:
        if fr.capacity > 0:
            facility_resources.setdefault(fr.facility_id, set()).add(fr.resource_id)
    

    return [FacilityPathways(facility_id=h.id, pathway_id=k, group_id=g) for h in list_facilities for g in A_idx for k in A_idx[g] \
            if pathway_resources[g][k] & facility_resources.get(h.id, set())]


def get_LinkedFacilities(list_facilities):
    return [LinkedFacilities(facility_id=h1.id, linked_facility_id=h2.id) for h1 in list_facilities for h2 in list_facilities]


def get_ActivityResources(t_gkal: dict, A_idx) -> list:
    unique = {}
    for g in A_idx:
        for k in A_idx[g]:
            for a in A_idx[g][k]:
                for l, cap in t_gkal[g][k][a].items():
                    if (g, k, a, l) not in unique:
                        unique[(g, k, a, l)] = cap
    return [ActivityResources(activity_id=a, pathway_id=k, group_id=g,resource_id=l, required_capacity=cap) 
            for (g,k, a, l), cap in unique.items()]

def get_CaseMixRatios(gdf_summary: pd.DataFrame, df_types_parcours: pd.DataFrame):
    """ Represents the lower bound on patients asssigments per patient group, per canton"""
    d_gr = {}
    df_groups = df_types_parcours.copy()
    df_groups = df_groups.groupby(["sej_type", "type_parcours"], as_index=False)["nb"].sum()
    for _, row in df_groups.iterrows():
        group = row["sej_type"] + "_" + row["type_parcours"].replace(" + ", "_")
        frac_visits  = row["nb"] / df_groups["nb"].sum()
        d_gr[group] = {}
        for _, gdf_row in gdf_summary.iterrows():
            can_code = gdf_row["can_code"]
            frac_pop = gdf_row["pop65p"] / gdf_summary["pop65p"].sum()   
            d_gr[group][can_code] = float( frac_visits * frac_pop) / 2
    return [CaseMixRatios(group_id=g, region_id=r, ratio=d_gr[g][r]) for g in d_gr.keys() for r in d_gr[g].keys()]

def get_TreatmentBounds(list_groups) -> list:
    return [TreatmentBounds(group_id=g.id, min_treatment_bound=0, max_treatment_bound=1) for g in list_groups]

def get_QualityBounds(quality_levels: dict, list_groups_ids):
    if len(set(quality_levels.values())) > 1 :  quality_objectives = {quality_levels["DOM"]: 0.75, quality_levels["HDJ"]:0.05,
                                                                      quality_levels["HCHDJ"]:0.05, quality_levels["HC"]:0.2 }
    else: quality_objectives = {"0": 1}
    return [QualityBounds(group_id=g, quality_id=u,
                          min_quality_bound=quality_objectives[u],
                          max_quality_bound=quality_objectives[u]) for g in list_groups_ids for u in list(set(quality_levels.values()))]


def get_pathways(df_types_parcours: pd.DataFrame):
    return list(df_types_parcours["SSR_TYPE"].unique())


def load_types_parcours(path: str, min_patients: int, dep_code:str):
    """Read and filter TYPES_PARCOURS for Loire."""
    df = pd.read_csv(path)
    df = reduce_TYPES_PARCOURS(df, min_patients, dep_code)
   
    return df

def load_mco_data(path: str, dep_code: str):
    """Read MCO data and keep Loire rows only."""
    df = pd.read_csv(path)
    df = df.rename(columns={'420': 'FI_ET'})
    df = df.fillna(0)
    df["PTRUE"] = 1
    return reduce_MCO_LOIRE(df, dep_code)

def load_ssr_data(path: str, dep_code: str):
    """Read SSR data and keep Loire SSR_A rows only."""
    df = pd.read_csv(path, sep=";")
    df = df.rename(columns={'FI': 'FI_ET'})
    df = df.fillna(0)
    return reduce_SSR_LOIRE(df, dep_code)

def load_data(dep_code:str):
    try:
        types_parcours = load_types_parcours(root_rawdata / "TYPES_PARCOURS.csv", 3, int(dep_code))
        df_mco = load_mco_data(root_rawdata / "MCO_2018r.csv", int(dep_code))
        df_ssr = load_ssr_data(root_rawdata / "SSR_2018r.csv", int(dep_code))
        if df_mco.empty or df_ssr.empty or types_parcours.empty:
            raise Exception(f"Data unavailable for department code: {dep_code}.")
    except Exception as e:
        raise(e)
        #raise Exception(f"Data unavailable for department code: {dep_code}.")
    return types_parcours, df_mco, df_ssr

def reduce_TYPES_PARCOURS(data: pd.DataFrame, min_patients: int, dep_code: str) -> pd.DataFrame:
    """Keep only Loire departments and groups with enough patients."""
    df = data[data['BEN_RES_DPT'] == dep_code].copy()
    df["SSR_TYPE"] = df["SSR_TYPE"].str.replace("_", "")
    df['SSR_TYPE'] = df['SSR_TYPE'].fillna('DOM')
    grouped = df.groupby(['BEN_RES_DPT', 'sej_type', 'type_parcours', 'SSR_TYPE'], as_index=False)['nb'].sum()
    grouped['group_key'] = grouped['sej_type'].astype(str) + grouped['type_parcours'].astype(str)
    totals = grouped.groupby('group_key')['nb'].transform('sum')
    filtered = grouped[totals >= min_patients].drop(columns='group_key')
    return filtered.reset_index(drop=True)


def reduce_MCO_LOIRE(data: pd.DataFrame, dep_code: str) -> pd.DataFrame:
    """Keep only rows corresponding to Loire department in MCO data. (FINESS number starts with 42)"""
    dept_code = data['FI_ET'].astype(str).apply(lambda s: int(s[:2]) if s[:2].isdigit() else 0)
    return data[dept_code.isin([dep_code])].reset_index(drop=True)


def reduce_SSR_LOIRE(data: pd.DataFrame, dep_code) -> pd.DataFrame:
    """Keep only SSR_A rows corresponding to Loire department"""
    dept_code = data['FI_ET'].astype(str).apply(lambda s: int(s[:2]) if s[:2].isdigit() else 0)
    return data[dept_code.isin([dep_code]) & (data['GDE'] == "SSR_A")].reset_index(drop=True)


def get_resources_capacities(t_gkal: dict, list_finess: list, df_types_parcours: pd.DataFrame, df_ssr: pd.DataFrame, df_mco: pd.DataFrame,
                             multiplier: float) -> dict:
    """Returns a dict with each available resource and its capacity given a finess number"""
    m_hl = {h: {} for h in list_finess}  
    m_hl = _get_resource_capacity(m_hl, list_finess,  df_mco, df_types_parcours, "CHIR/ORTHO", "JLI_CHI", 3)
    m_hl = _get_resource_capacity(m_hl, list_finess,  df_mco, df_types_parcours, "ANES", "JLI_CHI", 2)
    m_hl = _get_specialities_cap(m_hl, df_mco, df_types_parcours, list_finess)
    m_hl = _get_resource_capacity(m_hl, list_finess,  df_mco, df_types_parcours, "KINE_MCO", "ACTCLI_PM", {"PTG":10, "PTH":15})
    m_hl = _get_resource_capacity(m_hl, list_finess,  df_ssr,
                                df_types_parcours
                                    .assign(sej_type = \
                                            df_types_parcours["sej_type"].str.cat(df_types_parcours["SSR_TYPE"], sep="_")),
                                "DAY_HC", "JOUHC", post_op_scenarios["DAY_HC"])
    m_hl = _get_resource_capacity(m_hl, list_finess,  df_ssr,
                                df_types_parcours
                                    .assign(sej_type = \
                                            df_types_parcours["sej_type"].str.cat(df_types_parcours["SSR_TYPE"], sep="_")),
                                "KINE_SSR", "JOUHP", post_op_scenarios["KINE_SSR"])
    m_hl = _get_resource_capacity(m_hl, list_finess, None,
                                df_types_parcours
                                    .assign(sej_type = \
                                            df_types_parcours["sej_type"].str.cat(df_types_parcours["SSR_TYPE"], sep="_")),
                                "KINE_DOM", None, post_op_scenarios["KINE_DOM"])
    m_hl = _get_finance_capacity(m_hl, df_ssr, df_mco, t_gkal, df_types_parcours) 
    
    return {x: {l : int(m_hl[x][l] * multiplier) for l in m_hl[x]}for x in m_hl}


def _get_finance_capacity(m_hl, df_ssr: pd.DataFrame, df_mco: pd.DataFrame,
                          t_gkal: dict, df_types_parcours: pd.DataFrame) -> dict:
    """Calculate the financial need for every facility (including DOM and ORTHO center)"""
    
    df_visits = df_types_parcours.copy()
    df_visits["group"] = df_visits['sej_type'] +  "_" + df_visits['type_parcours'].str.replace(" + ", "_", regex=False)
    mco_finance = 0
    ssr_finance = 0
    dom_finance = 0
    standard_pathway = ["CHIR/ORTHO_pre", "ANES", "KINE_MCO", "CHIR/ORTHO+ANES", "CHIR/ORTHO_post"]

    for _, row in df_visits.iterrows():
        g = row["group"]
        k = row["SSR_TYPE"]
        
        for a in standard_pathway:
            mco_finance += t_gkal[g][k][a]["finance"] * row["nb"]
        if row["type_parcours"] != "standard":
            specialists_visits = row["type_parcours"].replace(" + ", "_").split("_")
            for s in specialists_visits:
                mco_finance += t_gkal[g][k][s]["finance"] * row["nb"]
        if k == "DOM":
            dom_finance += t_gkal[g][k]["KINE_DOM"]["finance"] * row["nb"]
        elif k == "HC":
            ssr_finance += t_gkal[g][k]["DAY_HC"]["finance"] * row["nb"]
        elif k == "HDJ":
            ssr_finance += t_gkal[g][k]["KINE_SSR"]["finance"] * row["nb"]
        elif k == "HCHDJ":
            ssr_finance += t_gkal[g][k]["KINE_SSR"]["finance"] * row["nb"]
            ssr_finance += t_gkal[g][k]["DAY_HC"]["finance"] * row["nb"]
       
        
    m_hl["DOM"]["finance"] = dom_finance
    for h in df_ssr["FI_ET"].unique():
        m_hl[h]["finance"] = ssr_finance  / len(df_ssr["FI_ET"].unique())
    for h in  df_mco["FI_ET"].unique():
        if h in df_ssr["FI_ET"].unique():
            m_hl[h]["finance"] += mco_finance / len(df_mco["FI_ET"].unique())
        else:
            m_hl[h]["finance"] = mco_finance  / len(df_mco["FI_ET"].unique())

    return m_hl

def _get_specialities_frac(df_mco: pd.DataFrame, list_finess: list) -> dict:
    """Returns approx of facilities' capacity for a speciality. When no info is availabile, we assume the speciality is always available
     (namely for GYNECO, URO, and ORL (flag field PTRUE=TRUE for all rows))"""
    total_cap_regional = {}
    
    for speciality in df_mco_flag_fields.keys():
        flag_field = df_mco_flag_fields[speciality]
        total_cap_regional[speciality] = sum(df_mco[df_mco[flag_field]!=0]["ACTCLI_PM"])

    facility_specialty_frac= {}
    for finess in list_finess:
        facility_specialty_frac[finess] = {}
        for speciality in df_mco_flag_fields.keys():
            flag_field = df_mco_flag_fields[speciality]
            if finess in list(df_mco["FI_ET"].unique()):
                if df_mco[df_mco["FI_ET"]==finess][flag_field].iloc[0] != 0:
                    facility_specialty_frac[finess][speciality] = \
                        df_mco[df_mco["FI_ET"]==finess]["ACTCLI_PM"].iloc[0] / total_cap_regional[speciality]
                else:
                    facility_specialty_frac[finess][speciality] = 0
            else:
                facility_specialty_frac[finess][speciality] = 0

    return facility_specialty_frac

def _get_specialities_cap(m_hl: dict, df_mco: pd.DataFrame, df_types_parcours: pd.DataFrame,
                          list_finess: list) -> dict:
    import copy
    
    frac_specialities =  _get_specialities_frac(df_mco, list_finess)
    nb_groups = {x:0 for x in specialities}
    
    for s in specialities:
        nb_groups[s] += df_types_parcours[df_types_parcours["type_parcours"].str.contains(s)]["nb"].sum()

    cap_specialities = copy.deepcopy(frac_specialities)
    for facility in df_mco["FI_ET"].unique():
        for speciality in specialities:
            if df_mco[df_mco["FI_ET"] == facility][df_mco_flag_fields[speciality]].iloc[0] != 0:
                cap_specialities[facility][speciality] = int(nb_groups[speciality] * frac_specialities[facility][speciality] + 1)
            else:
                cap_specialities[facility][speciality] = 0
    
    m_hl = _extend_nested_dict(m_hl, cap_specialities)
    return  m_hl



def _get_resource_capacity(m_hl_init: dict, list_finess: list, df_activity: pd.DataFrame, df_types_parcours: pd.DataFrame,
                           resource_name: str, resource_table_field: str, resource_consumption: dict) -> dict:
    """ 
    Facilities resource capacity calculated as total department consumption `total_consumption_resource` times
    the proportion of the facility's resource capacity over the total department resource capacity.
    # Hypothesis: all resources except specialists are present in all facilities by type either MCO or SSR   
    """
    import math
    m_hl = {h: {resource_name: 0} for h in list_finess}    
   
    if isinstance(resource_consumption, dict):
        df_types_parcours["resource_consumption"] = df_types_parcours["sej_type"].map(resource_consumption)
        total_consumption_resource = (df_types_parcours['resource_consumption'] * df_types_parcours['nb']).sum()
    else:
        total_consumption_resource = float((resource_consumption * df_types_parcours["nb"].sum()))
    #case dealing with the stay-at-home patients
    if df_activity is None:
         m_hl["DOM"][resource_name] = math.ceil(total_consumption_resource)
    else:  
        for h in list_finess:
            if h in df_activity["FI_ET"].unique():
                    total_dep_resources = df_activity[resource_table_field].sum()
                    current_facility_resources = df_activity[df_activity["FI_ET"]==h][resource_table_field].iloc[0]
                    # We assume that KINE_SSR and DAY_HC are present at every hospital
                    if current_facility_resources == 0 and resource_name not in {"KINE_SSR", "DAY_HC"}:
                        m_hl[h][resource_name] = 0
                    else:
                        capacity_resource = int(total_consumption_resource * ( current_facility_resources / total_dep_resources) + 1)
                        m_hl[h][resource_name] = capacity_resource
            else:
                current_facility_resources =  m_hl_init[h].get(resource_name, 0)    
            
    m_hl = _extend_nested_dict(m_hl_init, m_hl)
    return m_hl  


def _extend_nested_dict(init_dict: dict, ext_dict: dict):
    """Helper function to update capacity of m_hl with an extension containg capacity of new resources"""
    res_dict = {k: init_dict.get(k, {}) | ext_dict[k] for k in set(init_dict) | set(ext_dict)}
    return res_dict



def get_pop65p() -> pd.DataFrame:
    """ Returns a dataframe with the total population over 65 by Canton code and department code"""
    df_pop = pd.read_csv(root_deriveddata/ "pop65.csv", sep=";", low_memory=False)
    df_pop= df_pop[["codgeo", "pop65p"]]\
        .rename(columns = {"codgeo":"comm_code"})\
        .fillna(0)
    df_comm = pd.read_csv(root_opendata / "v_commune_2025.csv")
    df_comm = df_comm[["COM", "CAN", "DEP"]].rename(columns={"COM": "comm_code", "CAN": "can_code", "DEP": "dep_code"})
    df_merged = pd.merge(df_comm, df_pop, on="comm_code", how="inner").drop_duplicates()
    df_merged["pop65p"] = df_merged["pop65p"].astype(int)
    df_pop65p = df_merged.groupby(["can_code"], as_index=False).aggregate({
        "dep_code": "first",
        "pop65p": "sum"
    })
    return df_pop65p
    

def get_geo_polygon()->gpd.GeoDataFrame:
    """Returns a dataframe with the geographic polygon of each canton along with the total population"""
    gdf = gpd.read_file(root_opendata / "cantons_2015_simpl.json", engine="pyogrio")
    gdf["population"] = gdf["population"].astype(int)
    gdf["can_code"] = gdf["dep"].astype(str).str.zfill(2) + gdf["canton"].astype(str).str.zfill(2)
    gdf = gdf[["can_code", "bureau", "population", "dep", "geometry"]].drop_duplicates()
    gdf = gdf.rename(columns={"dep": "dep_code"})
    return gdf.to_crs("EPSG:4326")

def verify_department_finess(df_mco: pd.DataFrame, df_ssr: pd.DataFrame, df_finess: pd.DataFrame) -> Tuple[pd.DataFrame,pd.DataFrame]:
        df_mco = df_mco[df_mco["FI_ET"].isin(df_finess["nofinesset"])]
        df_ssr = df_ssr[df_ssr["FI_ET"].isin(df_finess["nofinesset"])]
        return df_mco, df_ssr

def get_finess_info(df_mco: pd.DataFrame, df_ssr: pd.DataFrame, gdf_geo: gpd.GeoDataFrame) -> pd.DataFrame:
    """Returns a dataframe with the canton code of each finess"""
    from pyproj import Transformer
    df_finess = pd.read_csv(root_deriveddata / "finess_2018.csv", sep=";", encoding="latin1",\
                            usecols=["nofinesset", "rs", "coordx", "coordy"],  dtype={"coordx": str, "coordy": str},\
                            low_memory=False)
    
    transformer = Transformer.from_crs(2154, 4326, always_xy=True)
    x = df_finess["coordx"].str.replace(",", "", regex=False).astype(float)
    y = df_finess["coordy"].str.replace(",", "", regex=False).astype(float)
    df_finess["lon"], df_finess["lat"] = transformer.transform(x.values,y.values)

    gdf_finess = gpd.GeoDataFrame(df_finess, geometry=gpd.points_from_xy(df_finess["lon"], df_finess["lat"]), crs="EPSG:4326")

    gdf_geo = gdf_geo[["can_code", "geometry"]].copy()
    gdf_geo.sindex
    gdf_finess = gpd.sjoin(gdf_finess,gdf_geo, how="left", predicate="intersects")
    all_finess = pd.concat([df_ssr["FI_ET"], df_mco["FI_ET"]]).dropna().unique()
    gdf_finess = gdf_finess[(gdf_finess["nofinesset"].isin(all_finess)) & (gdf_finess["can_code"].notnull())]
    
    return gdf_finess[["nofinesset", "rs", "lat","lon","can_code"]]

def pad_single(dep_code: str):
    if not dep_code.isdigit():
        raise("Unhandled department code number", dep_code)
    if int(dep_code) < 10 and len(dep_code) == 1:
        return "0" + dep_code
    return dep_code

def summarize_geo_data(gdf_cantons: gpd.GeoDataFrame, df_pop65p:pd.DataFrame, dep_code: str) ->gpd.GeoDataFrame:
    """Returns a dataframe of all the geographic information needed merged"""
    gdf_cantons = gdf_cantons.merge(df_pop65p, on= ["can_code","dep_code"], how="left")
    gdf_cantons = gdf_cantons[gdf_cantons["dep_code"] == pad_single(dep_code)]
    gdf_cantons.fillna(0)
    gdf_geo = gdf_cantons.dissolve(
        by="bureau",
        aggfunc= {
            "can_code": "first", 
            "dep_code": "first",
            "population": "sum",
            "pop65p": "sum"
    }).reset_index().rename(columns={"bureau":"nom"})
    #gdf_geo  = gdf_geo.explode(index_parts=False).reset_index(drop=True)
    gdf_geo["perc_65p"] = gdf_geo["pop65p"] / gdf_geo["population"] * 100
    gdf_geo["adjacent"] = [gdf_geo.loc[gdf_geo.geometry.touches(geom),"can_code"].to_list() for geom in gdf_geo.geometry]

    return gdf_geo

def get_region_affinities(gdf_summary: pd.DataFrame, list_Facilities: list[Facility], method: str ="OSRM") -> dict:
    """Returns a dict with the affinities of each facility to each region"""
    import numpy as np

    if method == "OSRM":
        print("Using OSRM distances to compute affinities")
        df_distances = pd.read_parquet(root_deriveddata / "distances_pthptg.parquet")
        df_dep_distances = df_distances[df_distances["dep_code"].isin(gdf_summary["dep_code"].unique())]
        w_rh = {can: dict(zip([x for x in df_dep_distances["nofinesset"].unique()], (1 / df_dep_distances[df_dep_distances["region"]==can]["distance"].values).astype(float)))\
                for can in df_dep_distances["region"].unique()}
        added = [f for f in list_Facilities if f.id not in df_dep_distances.nofinesset.unique()]
        gdf_proj = gdf_summary.to_crs(2154)
        added_coords = gpd.GeoSeries(gpd.points_from_xy([added[0].lon], [added[0].lat]), crs=4326).to_crs(2154).iloc[0]

        for r, c in zip(gdf_proj.can_code, gdf_proj.geometry.centroid):
            w_rh.get(r, {}).update({f.id: 1 / added_coords.distance(c) for f in added})
    else:
        print("Using Euclidean distances to compute affinities")
        gdf_proj = gdf_summary.to_crs("EPSG:2154") 
        longitudes = [x.lon for x in list_Facilities]
        latitudes = [x.lat for x in list_Facilities]
        facilities = gpd.GeoSeries(gpd.points_from_xy(longitudes, latitudes), crs="EPSG:4326").to_crs("EPSG:2154") 
        centroids = gdf_proj.geometry.centroid 
        dist_matrix = np.column_stack([facilities.distance(c) for c in centroids]) 
        w_rh = {can: dict(zip([x.id for x in list_Facilities], 1 / dist_matrix[:, i])) for i, can in enumerate(gdf_proj.can_code)}
    return w_rh


def get_orth_wrh(can_code, r, list_adjacent):
    if can_code == r:
        return 2
    elif can_code in list_adjacent.values[0]:
        return 1
    else: return 0.5

def get_activities_per_group_pathway(list_pathways_ids: list, list_groups_ids: list) -> dict:
    """Returns a dictionary with the activities for each group/pathway"""
    #STEP 1: CHIR/ORTHO (pre-op)
    #STEP 2: ANES (pre-op)
    #STEP 3: type_parcours consultations (optional specialties)
    #STEP 4: KINE_MCO (pre-op physiotherapy)
    #STEP 5: CHIR/ORTHO + ANES (surgery block)
    #STEP 6: Post-op KINE allocation (varies by scenario)
    #STEP 7: CHIR/ORTHO (final post-op)
    A_idx = {}
    for g in list_groups_ids:
        A_idx[g] = {}
        for k in list_pathways_ids:
            A_idx[g][k] = []
            A_idx[g][k].extend(["CHIR/ORTHO_pre", "ANES"])
            specialists_activities = g.split("_")[1:]
            if not "standard" in specialists_activities:
                A_idx[g][k].extend(specialists_activities)
            A_idx[g][k].extend(["KINE_MCO"])
            A_idx[g][k].extend(["CHIR/ORTHO+ANES"])
            for activity, scenarios in post_op_scenarios.items():
                for s in scenarios:
                    if str(g.split("_")[0] + "_" + k) == s and post_op_scenarios[activity][s] != 0:
                        A_idx[g][k].extend([activity])
            A_idx[g][k].extend(["CHIR/ORTHO_post"])
    return A_idx
    
def get_transferable(A_idx: dict) -> dict:
    """Returns a dictionary with the transferable activities for group g pathway k"""
    import copy
    transferable= copy.deepcopy(A_idx)
    for g in A_idx.keys():
        for k in A_idx[g].keys():
            transferable[g][k].pop()
            if k == "DOM":
                transferable[g][k].remove("KINE_DOM")          
    return transferable

def get_transfer_to(A_idx: dict) -> dict:
    """Returns a dictionary with the activities to transfer to for for group g pathway k"""
    import copy

    transfer_to= copy.deepcopy(A_idx)
    for g in A_idx.keys():
        for k in A_idx[g].keys():
            transfer_to[g][k].pop(0)
            if k == "DOM":
                transfer_to[g][k].remove("KINE_DOM")
            transfer_to[g][k] = {A_idx[g][k][i]: v for i,v in enumerate(transfer_to[g][k])}
    return transfer_to




def get_required_resources(A_idx, list_resources_ids):
    """Return a dictionary of dims groups x pathways x activities with required resources of each type"""
    default_activities_consumption = {"CHIR/ORTHO_pre": 1, "ANES": 1, "CHIR/ORTHO_post": 1} | {x : 1 for x in specialities}
    dict_required_resources = {}
    finance_costs_rescaled = rescale_costs(finance_costs.copy())
    for g in A_idx.keys():
        main_group = g.split("_")[0]
        dict_required_resources[g] = {}
        for k in A_idx[g].keys():
            dict_required_resources[g][k]={}
            for a in A_idx[g][k]:
                dict_required_resources[g][k][a] = {l:0 for l in list_resources_ids}
                if "pre" in a or "post" in a:
                    l = a.split("_")[0]
                else: l = a
                if a in default_activities_consumption :
                    dict_required_resources[g][k][a][l] = default_activities_consumption[a]
                    dict_required_resources[g][k][a]["finance"] = finance_costs_rescaled[main_group][a]
                elif a in post_op_scenarios:
                    dict_required_resources[g][k][a][l] = post_op_scenarios[a][ main_group + "_" + k]
                    dict_required_resources[g][k][a]["finance"] = post_op_scenarios[a][ main_group + "_" + k] * finance_costs_rescaled[main_group][a]
                elif a == "KINE_MCO":
                    dict_required_resources[g][k][a][l] = nb_kine_preop[main_group]
                    dict_required_resources[g][k][a]["finance"] = nb_kine_preop[main_group] * finance_costs_rescaled[main_group][a]
                elif a == "CHIR/ORTHO+ANES":
                    dict_required_resources[g][k][a]["CHIR/ORTHO"] += 1
                    dict_required_resources[g][k][a]["ANES"] += 1
                    dict_required_resources[g][k][a]["finance"] = finance_costs_rescaled[main_group][a]

    return dict_required_resources


def get_facility_visits(nofinesset, df_mco, df_ssr):
    nbr_visits = 0
    if nofinesset in df_mco["FI_ET"].unique():
        row_mco = df_mco[df_mco["FI_ET"] == nofinesset].iloc[0]
        nbr_visits += row_mco["SEJHC_MCO"] + row_mco["SEJ0_MCO"] + row_mco["SEJHP_MCO"]
    if nofinesset in df_ssr["FI_ET"].unique():
        row_ssr = df_ssr[df_ssr["FI_ET"] == nofinesset].iloc[0]
        nbr_visits += row_ssr["SEJHC"]
    return int(nbr_visits)

def get_default_geo_info(gdf_geo):
    """return the default region code and coordinates for DOM and ORTH facilities"""
    can_code_largest = gdf_geo[gdf_geo["population"]==gdf_geo["population"].max()]["can_code"].iloc[0]
    centroid = gdf_geo.geometry.iloc[gdf_geo["population"].idxmax()].centroid
    coordinates = [centroid.x, centroid.y]
    return can_code_largest, coordinates

def get_frac_resource_capacities(m_hl, p_orth:float) -> dict:
    """Calculate the ORTHOPEDIC center resource capacities as a percentage of the other facilities capacities"""
    frac_resources = {l: p_orth * sum(m_hl[h][l] for h in m_hl.keys()) for l in next(iter(m_hl.values())).keys()}
    frac_resources["KINE_DOM"] = 0
    return frac_resources

def getFacilityType(nofinesset, df_mco, df_ssr):
    if nofinesset in df_mco["FI_ET"].unique() and nofinesset in df_ssr["FI_ET"].unique():
        return "Other"
    elif nofinesset in df_mco["FI_ET"].unique():
        return "MCO"
    elif nofinesset in df_ssr["FI_ET"].unique():
        return "SSR"
    else:
        return "Other"