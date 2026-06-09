# panda-wnscript

Transformations running on PanDA worker nodes.

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

## Release Notes

See [ChangeLog.txt](ChangeLog.txt)