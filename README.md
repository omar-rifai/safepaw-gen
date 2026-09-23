## Optimizing Case-Mix Planning at the Territorial Level: A Pathway-Centered and Resource-Aware Approach
### Data Generation Tool

Tool to generate instance for SAFEPAW casemix optimization.

> [!TIP]
> The dependencies in this project are managed with `pixi`.  to install, you can run `curl -fsSL https://pixi.sh/install.sh | sh`

#### Quick Start

````
safepaw-gen <maternities|ptgpth|burdett> [dep_code]
````

where `<dep_code>` is an French INSEE department code is needed for `maternties`and `ptgpth` instances. The json files are stored in the `outputs` directory.

