import typer
from typing import Literal
from .mappers.datasets_mappers.maternities_serializer import serialize_maternities
from .mappers.datasets_mappers.ptgpth_serializer import serialize_ptgpth
from .mappers.datasets_mappers.burdett_serializer import serialize_burdett



def cli(instance : Literal["maternities", "ptgpth","burdett"] = typer.Argument(None, help="type of data to generate from (maternities, burdett, ptgpth)"),
        dep_code: str | None = typer.Argument(None, help="French department code to generate data from, if relevant")):
   

    if instance is None:
        typer.echo("Usage: safepaw-gen <maternities|ptgpth|burdett> [dep_code]")
        raise typer.Exit()

    print(f"Generating {instance} instance..")
    match instance:
        case 'maternities':
            if dep_code is None:
                raise typer.BadParameter("dep_code is required for maternities instances")
            serialize_maternities(region_code=None, dep_code=dep_code, save_params=True, global_multiplier_demand=1,
                                  global_multiplier_capacity=1, global_perc_transfers=0)
        case 'burdett':
            serialize_burdett(perc_allowed=0, save_params=True)
        case 'ptgpth':
            if dep_code is None:
                            raise typer.BadParameter("dep_code is required for ptgpth instances")
            serialize_ptgpth(dep_code=dep_code, p_transf=1, p_orth=0, resources_mult=1, quality_requirement=False,
                             global_multiplier_demand=1, global_multiplier_capacity=1, global_perc_transfers=0, save_params=True)
    return


def main():
    typer.run(cli)



    
