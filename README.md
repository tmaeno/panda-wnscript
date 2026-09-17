# panda-wnscript

Transformations running on PanDA worker nodes.

> [!WARNING]
> This package must remain Python 2 compatible. Scripts are deployed to and executed on worker nodes that may run old container images with Python 2 as the only available interpreter. Do not use Python 3-only syntax or standard library features.

## Installation

```bash
git clone git://git@github.com/PanDAWMS/panda-wnscript.git
cd panda-wnscript
./make.sh
git add dist/
git commit -m "Build binaries"
git push
```

`make.sh` packages each transformation into a self-extracting executable under `dist/`. Each executable is a shell stub prepended to a zip archive containing the Python source and utilities; it extracts and runs itself at execution time. The built binaries in `dist/` must be committed to the repository - a script running on the ATLAS PanDA servers periodically pulls this repository and picks up the binaries, which are then distributed to worker nodes on demand.

## Repository structure

```
src/          # source for each transformation, one subdirectory per script
pandawnutil/  # shared utility library bundled into every executable
dist/         # built self-extracting binaries (committed, deployed from here)
template/     # shell stubs prepended to zip archives during build
```

## Available scripts

| Script | Description |
|--------|-------------|
| `runGen` | General-purpose payload execution on the worker node |
| `runAthena` | Runs Athena (the ATLAS offline framework) jobs |
| `buildGen` | Builds user code and libraries in a generic environment |
| `buildJob` | Builds user code in an Athena/CMT/CMake environment |
| `runMerge` | Merges output files |
| `runHPO` | Hyperparameter optimisation payload runner |
| `preGoodRunList` | Filters events against a Good Run List (GRL) using CVMFS |
| `runcontainer` | Runs payloads inside a Singularity/Apptainer container |

Each script in `src/<name>/` has a `version` file that determines the name of the corresponding binary in `dist/`.

The shared `pandawnutil/` library provides utilities common to all scripts: misc helpers, error codes, ROOT setup, file staging, job tracing, and logging.

## End-to-end tests

New binaries can be tested locally before being deployed to the PanDA server.
However, these tests only exercise the binaries themselves in isolation. They do not verify communication with the pilot or identify potential side effects on upstream components.

The following procedure can be used to perform an end-to-end test.

First, push the new binary to dist/ on GitHub. For example:
```
git add dist/runGen-dev dist/runMerge-dev
git commit
git push
```
The new binaries will be automatically deployed to the PanDA server nodes within approximately one hour.
Once the deployment is complete, the binaries can be used for an end-to-end test. For example:
Then, e.g,
```
prun --exec "cp -L %IN output.root" --nFiles 1 --transPath http://pandaserver.cern.ch:25080/trf/user/runGen-dev --inDS blah --outDS blah --output output.root --mergeOutput --mergeTransPath http://pandaserver.cern.ch:25080/trf/user/runMerge-dev --forceStaged --useAthenaPackages
```
This runs the new binaries through the normal PanDA workflow, allowing them to be thoroughly tested before replacing the production binaries.

To deploy the tested binaries to production, copy them to the current version tags and push them to GitHub. For example:
```
cp dist/runGen-dev dist/runGen-00-00-02
cp dist/runMerge-dev dist/runMerge-00-00-02
git add dist/runGen-00-00-02 dist/runMerge-00-00-02
git commit
git push
```