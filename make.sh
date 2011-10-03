#!/bin/bash

WORKDIR=$PWD
SRCDIR=$WORKDIR/src
DISTDIR=$WORKDIR/dist
BUILDDIR=$WORKDIR/build
TEMPLATEDIR=$WORKDIR/template

TMPZIP=$BUILDDIR/tmp.zip

# initial cleanup
mkdir -p $DISTDIR
mkdir -p $BUILDDIR
rm -rf $DISTDIR/*
rm -rf $BUILDDIR/*

# loop over all target
for TARGET in "runGen"
  do
  EXESRCDIR=$SRCDIR/`echo $TARGET | tr "[A-Z]" "[a-z]"`
  EXENAME=$DISTDIR/$TARGET-`cat $EXESRCDIR/version`
  rm -f $TMPZIP
  # include utils
  zip -o $TMPZIP -R pandawnutil "*.py" "*.c"
  # script main
  cd $EXESRCDIR
  zip -o $TMPZIP -R . "*.py"
  cd $WORKDIR
  # make self-exracting executable
  cat $TEMPLATEDIR/zipheader $TMPZIP > $EXENAME
  chmod +x $EXENAME
done
