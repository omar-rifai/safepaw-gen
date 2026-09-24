import typer
from typing import Literal
from .mappers.datasets_mappers.maternities_serializer import serialize_maternities



def cli(instance : Literal["maternities"] = typer.Argument(None, help="type of data to generate. Current available options: [maternities]"),
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
        case _:
             raise typer.BadParameter("Unavailable instance type. aborting.")
    return


def main():
    typer.run(cli)



    
