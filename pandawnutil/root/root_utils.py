# get ROOT version and setup strings
def get_version_setup_string(root_ver, cmt_config):
    if not root_ver:
        return '', ''
    rootVer = root_ver
    if rootVer.count('.') != 2:
        rootVer += ".00"
    # CVMFS version format
    if not cmt_config:
        print ("Use i686-slc5-gcc43-opt for ROOT by default when --cmtConfig is unset")
        rootCVMFS = rootVer + '-' + 'i686-slc5-gcc43-opt'
    else:
        rootCVMFS = rootVer + '-' + cmt_config
    # setup string
    tmpSetupEnvStr = ("export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase; "
                      "source $ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh --quiet; "
                      "source $ATLAS_LOCAL_ROOT_BASE/packageSetups/atlasLocalROOTSetup.sh "
                      "--rootVersion={0} --skipConfirm; ").format(rootCVMFS)
    return rootCVMFS, tmpSetupEnvStr
