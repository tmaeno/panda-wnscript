#!/bin/bash
#
# Build script for panda-wnscript worker node executables.
#
# Each target is packaged as a self-extracting executable by prepending a shell
# stub (zipheader) to a zip archive. The stub extracts the zip at runtime and
# invokes the payload. Output executables are written to dist/ and named
# <TARGET>-<version> (version read from src/<target>/version).
#
# Usage: ./make.sh
#

WORKDIR=$PWD
SRCDIR=$WORKDIR/src
DISTDIR=$WORKDIR/dist
BUILDDIR=$WORKDIR/build
TEMPLATEDIR=$WORKDIR/template

TMPZIP=$BUILDDIR/tmp.zip

BUID_TIMESTAMP=`date -u "+%F %T UTC"`

# clean previous build artifacts
mkdir -p $DISTDIR
mkdir -p $BUILDDIR
rm -rf $DISTDIR/*
rm -rf $BUILDDIR/*

# embed build timestamp into pandawnutil so executables can report when they were built
echo build_timestamp="\"$BUID_TIMESTAMP\"" > pandawnutil/build_timestamp.py

# Python-only targets: zip pandawnutil + target source (*.py, *.c only)
for TARGET in "runGen" "buildGen" "runAthena" "buildJob" "runHPO"
  do
  echo "Start " $TARGET
  EXESRCDIR=$SRCDIR/`echo $TARGET | tr "[A-Z]" "[a-z]"`
  EXENAME=$DISTDIR/$TARGET-`cat $EXESRCDIR/version`
  rm -f $TMPZIP
  # include utils
  zip -o $TMPZIP -R pandawnutil "*.py" "*.c"
  # script main
  cd $EXESRCDIR
  zip -o $TMPZIP -R . "*.py"
  cd $WORKDIR
  # make self-extracting executable
  cat $TEMPLATEDIR/zipheader $TMPZIP > $EXENAME
  chmod +x $EXENAME
  echo
done

# Targets that include non-Python files (e.g. shell scripts, data files)
for TARGET in "runMerge"
  do
  echo "Start " $TARGET
  EXESRCDIR=$SRCDIR/`echo $TARGET | tr "[A-Z]" "[a-z]"`
  EXENAME=$DISTDIR/$TARGET-`cat $EXESRCDIR/version`
  rm -f $TMPZIP
  # include utils
  zip -o $TMPZIP -r pandawnutil -i "*.py" "*.c"
  # script main - include all file types
  cd $EXESRCDIR
  zip -o $TMPZIP -r . -i *
  cd $WORKDIR
  # make self-extracting executable
  cat $TEMPLATEDIR/zipheader $TMPZIP > $EXENAME
  chmod +x $EXENAME
  echo
done

# Targets that include non-Python files and require CVMFS environment setup at runtime
for TARGET in "preGoodRunList"
  do
  echo "Start " $TARGET
  EXESRCDIR=$SRCDIR/`echo $TARGET | tr "[A-Z]" "[a-z]"`
  EXENAME=$DISTDIR/$TARGET-`cat $EXESRCDIR/version`
  rm -f $TMPZIP
  # include utils
  zip -o $TMPZIP -r pandawnutil -i "*.py" "*.c"
  # script main - include all file types
  cd $EXESRCDIR
  zip -o $TMPZIP -r . -i *
  cd $WORKDIR
  # make self-extracting executable with CVMFS-aware header
  cat $TEMPLATEDIR/zipheaderCVMFS $TMPZIP > $EXENAME
  chmod +x $EXENAME
  echo
done

# Targets that are standalone scripts - copied directly without zip packaging
for TARGET in "runcontainer"
  do
  echo "Start " $TARGET
  EXESRCDIR=$SRCDIR/`echo $TARGET | tr "[A-Z]" "[a-z]"`
  EXENAME=$DISTDIR/$TARGET
  cp $EXESRCDIR/$TARGET $EXENAME
  chmod +x $EXENAME
  echo
done
