Cocat can be installed through [PyPI](https://pypi.org) or [conda-forge](https://conda-forge.org).

## With `pip`

```bash
pip install cocat
```

## With `micromamba`

We recommend using `micromamba` to manage `conda-forge` environments (see `micromamba`'s
[installation instructions](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)).
First create an environment, here called `my_env`, and activate it:
```bash
micromamba create -n my_env
micromamba activate my_env
```
Then install `cocat`.
```bash
micromamba install cocat
```

## Development install

You first need to clone the repository:
```bash
git clone https://github.com/SciQLop/cocat
cd cocat
```
If you use `conda` environments, you will need to install `pip` first:
```bash
micromamba create -n cocat-dev
micromamba activate cocat-dev
micromamba install pip
```
Then install `cocat` in editable mode:
```bash
pip install -e .
```
