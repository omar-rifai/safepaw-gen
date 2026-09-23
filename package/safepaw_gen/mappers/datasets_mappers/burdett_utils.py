from lark import Lark, Transformer
import pandas as pd
import re

"""
Docstring pour backend.core.mappers.datasets_mappers.burdett_utils

list_facility_affinities_rows = get_FacilityAffinity(instance)
        list_facility_resources = get_FacilityResources(instance, max_transferable_in=10, max_transferable_out=1)
        list_facility_pathways = get_FacilityPathways(list_facilities)
        list_linked_facilities = get_LinkedFacilities(list_facilities)
        list_activity_resources = get_ActivityResources()
        list_case_mix_ratios = get_CaseMixRatios(instance)
        list_treatment_bounds = get_TreatmentBounds(list_patients)
        list_quality_bounds = get_QualityBounds(list_patients)
"""


hospitals = {
    "BPH": {"name": "Brisbane Private Hospital", "lon": "153.0226", "lat": "-27.4646"},
    "GCUH": {"name": "Gold Coast University Hospital", "lon": "153.3819", "lat": "-27.9595"},
    "GCPR": {"name": "Gold Coast Private", "lon": "153.3853", "lat": "-27.9622"},
    "JFN": {"name": "John Flynn Private", "lon": "153.488510", "lat": " -28.153879"},
    "LOG": {"name": "Logan Hospital", "lon": "153.1418", "lat": "-27.6700"},
    "NW": {"name": "North West Hospital", "lon": "152.9929", "lat": "-27.3940"},
    "PA": {"name": "Princess Alexandra", "lon": "153.0332", "lat": "-27.4990"},
    "PIN": {"name": "Pindara Hospital", "lon": "153.390936", "lat": "-28.0070776"},
    "PRCH": {"name": "Prince Charles Hospital", "lon": "153.0234", "lat": "-27.3899"},
    "QE2": {"name": "Queen Elizabeth 2 Jubilee", "lon": "153.0489", "lat": "-27.5594"},
    "RBWH": {"name": "Royal Brisbane & Women's", "lon": "153.0282", "lat": "-27.4471"},
    "RED": {"name": "Redland Hospital", "lon": "153.2521", "lat": "-27.5405"},
    "ROB": {"name": "Robina Hospital", "lon": "153.3760", "lat": "-28.0711"},
    "STAN": {"name": "St Andrews", "lon": "153.021088", "lat": "-27.461105"},
    "WES": {"name": "West Hospital", "lon": "152.9978", "lat": "-27.4778"}
}


def get_FacilityAffinity(list_facilities):
    from ...data_models.input_models import FacilityAffinity
    list_facility_affinities_rows = []
    for f in list_facilities:
        list_facility_affinities_rows.append(FacilityAffinity(
            facility_id=f.id,
            region_id="qld",
            affinity_score=1.0
        ))
    return list_facility_affinities_rows

def get_FacilityResources(list_facilities, list_resources, df_resources, perc_allowed:float):
    from ...data_models.input_models import FacilityResources
    list_facilityResources = []
    
    b_hl_in, b_hl_out = _get_facilities_max_transfers(list_facilities, perc_allowed)

    for f in list_facilities:
        dict_capacities = _get_facility_capacities(f.id, df_resources)
        for r in list_resources:
            list_facilityResources.append(FacilityResources(
                facility_id=f.id,
                resource_id=r.id,
                capacity=dict_capacities.get(r.id, 0),
                max_transferable_in=b_hl_in[f.id][r.id],
                max_transferable_out=b_hl_out[f.id][r.id]
            ))
    return list_facilityResources


def get_FacilityPathways(list_facilities, df_pathways):
    from ...data_models.input_models import FacilityPathways
    list_facilityPathways = []
    for f in list_facilities:
        pathways = _get_facility_pathways(df_pathways, f.id)
        for p in pathways:
            list_facilityPathways.append(FacilityPathways(
                facility_id=f.id,
                pathway_id=p,
                group_id=df_pathways[df_pathways["pathway_id"] == p]["patient_group_id"].iloc[0]
            ))
    return list_facilityPathways


def get_LinkedFacilities(list_facilities):
    from ...data_models.input_models import LinkedFacilities
    list_linkedFacilities = []
    for f in list_facilities:
        linked_facilities = [f2.id for f2 in list_facilities if f.id.split("_")[0] == f2.id.split("_")[0]]
        for lf in linked_facilities:
            list_linkedFacilities.append(LinkedFacilities(
                facility_id=f.id,
                linked_facility_id=lf
            ))
    return list_linkedFacilities


def get_ActivityResources(df_pathways: pd.DataFrame) -> list:
    from ...data_models.input_models import ActivityResources
    list_activityResources = []
    df_pathways = df_pathways[["pathway_activity", "pathway_id", "patient_group_id", "resource_id", "resource_consumption"]].drop_duplicates()
    for _, row in df_pathways.iterrows():
        required_resources = _get_activity_resources(row)
        for r_id, consumption in required_resources.items():   
            list_activityResources.append(ActivityResources(
                activity_id=row["pathway_activity"],
                pathway_id = row["pathway_id"],
                group_id = row["patient_group_id"],
                resource_id=r_id,
                required_capacity=consumption
            ))
    return list_activityResources


def get_CaseMixRatios(data: dict, df_pathways: pd.DataFrame) -> list:
    from ...data_models.input_models import CaseMixRatios
    list_caseMixRatios = []
    d_gr = _get_demand_lower_bound(df_pathways, data)
    for g in d_gr.keys():
        for r in d_gr[g].keys():
            ratio = d_gr[g][r]
            list_caseMixRatios.append(CaseMixRatios(group_id=g, region_id = r,ratio=ratio))
    return list_caseMixRatios


def get_TreatmentBounds(list_patientsGroups: list, data: dict) -> list:
    from ...data_models.input_models import TreatmentBounds
    list_treatmentBounds = []
    under_q_g = _get_under_q_g(data)
    for g in list_patientsGroups:
        list_treatmentBounds.append(TreatmentBounds(
            group_id=g.id,
            min_treatment_bound=under_q_g[g.id],
            max_treatment_bound=1
        ))
    return list_treatmentBounds


def get_QualityBounds(data:dict, df_pathways: pd.DataFrame) -> list:
    from ...data_models.input_models import QualityBounds
    list_qualityBounds = []
    under_q_gu = over_q_gu = _get_under_over_q_gu(data, df_pathways)
    for g in under_q_gu.keys():
        list_qualities = df_pathways[df_pathways["patient_group_id"]==g]["pathway_idx"].unique()
        for u in list_qualities:
            list_qualityBounds.append(QualityBounds(
                group_id=g,
                quality_id=str(u),
                min_quality_bound=under_q_gu[g][str(u)],
                max_quality_bound=over_q_gu[g][str(u)],
        ))
    return list_qualityBounds


def _get_facilities_max_transfers(facilities, perc_allowed):
    resources = ["cap_OT", "cap_ICU", "cap_Ward"]
    b_hl_in = {h.id: {r: 0 if perc_allowed == 0 else 2 for r in resources } for h in facilities}
    b_hl_out = {h.id: {r: perc_allowed for r in resources} for h in facilities}
    return b_hl_in, b_hl_out

def _get_facility_capacities(fid: str, df_resources: pd.DataFrame) -> dict:
    capacities = {"cap_OT": 0, "cap_ICU": 0, "cap_Ward": 0}
    x = df_resources[df_resources["facility"]==fid][["cap"]].iloc[0]
    r_type = df_resources[df_resources["facility"]==fid]["type"].iloc[0]
    capacities["cap_" + str(r_type)] =  int(x["cap"])
    return capacities

def _get_facility_pathways(df_pathways: pd.DataFrame, fid) -> list:
    """ get the pathways associated with a facility"""
    pathways = list(df_pathways[df_pathways["facility_id"] == fid]["pathway_id"].unique())
    return pathways

def _get_under_q_g(data:dict) -> dict:
    G = data["G"]
    values = [round(data["casemix"][i]/100.,4) for i in range(len(G))]
    under_q_g = {g: v for g, v in zip(G, values)}
    return under_q_g

def _get_under_over_q_gu(data: dict, df_pathways: pd.DataFrame):
    """Return the values for under and over q_gu as the submix for that particular pathway (=DRGs)"""
    unique_groups = data["G"]
    lines = 0
    under_q_gu = {}
    for _, g in enumerate(unique_groups):
        under_q_gu[g] = {}
        list_qualities = df_pathways[df_pathways["patient_group_id"]==g]["pathway_idx"].unique()
        for j, u in enumerate(list_qualities):
            if j < len(list_qualities) - 1:
                value = round(data["submix"][lines + j]/100.,4)
                under_q_gu[g][str(u)]  = value
            else:
                last_value = 1 - sum(under_q_gu[g].values())
                under_q_gu[g][str(u)] = last_value
            
            
        lines += len(df_pathways[df_pathways["patient_group_id"]==g]["pathway_idx"].unique())
    return under_q_gu


def _get_demand_lower_bound(df_pathways, data: dict) -> dict:
    groups = list(df_pathways["patient_group_id"].unique())
    regions = ["qld"]
    d_gr = {g: {r: 0 for r in regions } for g in groups}
    return d_gr

def _get_group_pathways(df_pathways:pd.DataFrame, gid)->list:
    """get list of possible pathways for group with id gid"""
    pathways = list(df_pathways[df_pathways["patient_group_id"] == gid]["pathway_id"].unique())
    return pathways



def _get_activity_resources(row: tuple) -> dict:
    """Retruns the needed resource consumption of this activity"""
    
    resources = ["cap_OT", "cap_ICU", "cap_Ward"]
    required = {r: 0 for r in resources}
    
    consumption =row["resource_consumption"]
    resource = row["resource_id"]
    required[resources[resource - 1]] = consumption
    return required


def _get_df_resources(data: dict) -> pd.DataFrame:
    import pandas as pd
    rows = []
    for x in data["INFO"]:
        rows.append({"facility": x[1], "type": _get_resource_type(x[1].split("_")[1]), "cap": x[2]*x[3]*data["nbWeeks"]})
    return pd.DataFrame(rows)

def _get_resource_type(suffix:str)->str:
    if suffix == "ICU" or suffix == "OT":
        return suffix
    else:
        return "Ward"
    


def _define_grammar():
    parser = Lark(r"""
                      start :(statement)*
                      statement: NAME "=" value [";"]
                      profile_entry : SPECIALTY "[" CAT "]" block
                      ?value : tuple
                             | block
                             | list
                             | NUMBER
                             | profile_entry
                             | NAME
                      list : "[" (value [","])* "]"
                      block : "{" value ("," value)* ","? "}"   
                      tuple: "<" value ("," value)* ">"
                      SPECIALTY.2: /[A-Z]\d{2,}[a-zA-Z]?(_[A-Z])?(?:\|[A-Z])*/
                      CAT: /(SUR|MED)(-AVG)?/
                      NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
                      NUMBER: /-?\d+(\.\d+)?/
                           
                      %ignore /\s+/

    """)
    return parser


class TreeToJSON(Transformer):
    def start(self, items):
        return dict(items)

    def statement(self, items):
        key = str(items[0])
        value = items[1]
        return (key, value)

    def NAME(self, token):
        return str(token)

    def NUMBER(self, token):
        return float(token) if '.' in token else int(token)

    def list(self, items):
        return list(items)

    def block(self, items):
        return list(items)

    def tuple(self, items):
        return list(items)
    
    def profile_entry(self, items):
        key = str(items[0])  # F01A|B
        category = str(items[1])  # SUR
        value = items[2]  # the block of CARD/ENDO entries
        return {'key': key, 'category': category, 'entries': value}
        


def _get_df_pathways(data: dict) -> pd.DataFrame:
    """Converts the list of pathway dictionaries into a pandas Dataframe
    for easier querying"""
    import pandas as pd
    rows = []
    for pathway in data["profile"]:
        pathway_id = pathway["key"]
        category = pathway["category"]
        entries = pathway["entries"]

        for entry in entries:
            group_id, pathway_idx, resource_id, resource_consumption, facilities = entry

            for facility_id in facilities:
                rows.append({
                    "pathway_id": pathway_id,
                    "category": category,
                    "patient_group_id": group_id,
                    "pathway_idx": pathway_idx,
                    "resource_id": resource_id,
                    "resource_consumption": resource_consumption,
                    "facility_id": facility_id,
                })
    df = pd.DataFrame(rows)

    return df


def _remove_trailing_comments(data):
    # Remove block comments /* ... */
    data = re.sub(r'/\*.*?\*/', '', data, flags=re.S)
    data = _preserve_specialty_lines(data)
    # Remove any remaining inline comments
    data = re.sub(r'//.*', '', data)
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in data.splitlines()]
    # Remove empty lines
    lines = [line for line in lines if line]
    # Join back into a single string
    return "\n".join(lines)

def _preserve_specialty_lines(data):
    # This matches lines that start with // and a specialty code, optional category
    pattern = r'^\s*//([A-Z]\d{2}[A-Z]?(?:\|[A-Z]){0,2}(?:\s*\[[A-Z]+\])?)'
    # Remove the leading //
    return re.sub(pattern, r'\1', data, flags=re.M)
