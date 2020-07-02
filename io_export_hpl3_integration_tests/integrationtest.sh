#!/bin/bash

# USAGE: ./integrationtest (testname) [build/gui/approve]
# "build"   - Only loads up the file with the newest addon (for creating a test)
# "gui"     - Runs the test and brings up blender
# "approve" - Copy the newly-generated md5 hashes to checksums.txt

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd)"
cd $DIR
BLENDER="/c/Program Files/Blender Foundation/Blender 2.83/blender.exe"

function runTest {
    NC='\033[0m' # No Color
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    TEST_BLEND_FILE=$1
    TEST_PATH="$(dirname "$(pwd)/$TEST_BLEND_FILE")"
    rm -r "$TEST_PATH/tmp"
    mkdir "$TEST_PATH/tmp"
    if [[ -d "$TEST_PATH/existing" ]]; then
        cp -r "$TEST_PATH/existing" "$TEST_PATH/tmp"
        mv "$TEST_PATH/tmp/existing" "$TEST_PATH/tmp/existing_tmp"
        mv "$TEST_PATH/tmp/existing_tmp" "$TEST_PATH"
        rm -r "$TEST_PATH/tmp"
        mv "$TEST_PATH/existing_tmp" "$TEST_PATH/tmp"
    fi
    # Copy map dir into tmp directory if it exists
    if [[ -d "$TEST_PATH/map" ]]; then
        cp -r "$TEST_PATH/map" "$TEST_PATH/tmp"
    fi
    HIDE_GUI="-noaudio --background --python-exit-code 1"
    if [[ "$2" == "gui" ]]; then
        HIDE_GUI=""
    fi
    if [[ "$2" == "build" ]]; then
        HIDE_GUI=""
        BUILD="true"
    fi
    TEST_PATH=$TEST_PATH BUILD=$BUILD "$BLENDER" $HIDE_GUI --log-level 0 $TEST_BLEND_FILE \
    --python ./utils/disable_addons.py \
    --python ../io_export_hpl3.py \
    --python ./utils/set_export_paths.py

    if [[ $? -ne 0 ]]; then
        printf "${RED}Test $(dirname $1) failed! Blender exited with error${NC}\n"
        exit 1
    fi

    # Match checksums
    DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd | sed "s;\/.\/;;g")"
    CUR_CKSUMS=""
    for i in $(find $TEST_PATH/tmp -type f); do
        FILE=$(basename $i)
        # Strip creation/modification date from files
        EXT="${FILE##*.}"
        if [[ "$EXT" == "dae" ]]; then
            DAE=$(sed 's:<created>.*</created>::g' "$i")
            echo "$DAE" > "$i"
            DAE=$(sed 's:<modified>.*</modified>::g' "$i")
            echo "$DAE" > "$i"
            DAE=$(sed 's:<authoring_tool>.*</authoring_tool>::g' "$i")
            echo "$DAE" > "$i"
            DAE=$(sed "s;\/.:\/;;g" "$i")
            echo "$DAE" > "$i"
            DAE=$(sed "s;${DIR};;g" "$i")
            echo "$DAE" > "$i"
        fi
        if [[ "$EXT" == hpm* ]]; then
            echo "Sanitizing $i"
            DAE=$(sed 's:CreStamp="[0-9]*":CreStamp="":g' "$i")
            echo "$DAE" > "$i"
            DAE=$(sed 's:ModStamp="[0-9]*":ModStamp="":g' "$i")
            echo "$DAE" > "$i"
        fi
        CKSUM=$(cat $i | md5sum)

        CUR_CKSUMS=$(echo -e "$CUR_CKSUMS\n$FILE=$CKSUM")
    done
    if [[ "$2" == "approve" ]]; then
        echo "$CUR_CKSUMS" > "$TEST_PATH/checksums.txt"
    fi
    SAVED_CKSUMS=$(cat "$TEST_PATH/checksums.txt" | tr -d '\015')
    if [[ "$SAVED_CKSUMS" != "$CUR_CKSUMS" ]]; then
        printf "${RED}Test $(dirname $1) failed! Checksums do not match${NC}\n"
        echo "SAVED------"
        echo  "$SAVED_CKSUMS"
        echo "NEW--------"
        echo "$CUR_CKSUMS"
        echo
        diff --color <(echo "$SAVED_CKSUMS") <(echo  "$CUR_CKSUMS")
        exit 1
    else
        printf "${GREEN}Test $(dirname $1) success${NC}\n"
    fi
}

declare -A TESTS

# 01_multiex_multitex
# export mul to multi, multi tex set = should be each material as own
# including split objects
TESTS["01_multiex_multitex"]="./materials/01_multiex_multitex/01_multiex_multitex.blend"

# 02_multiex_singletex
# export mul to multi, single tex set = each object has 1 tex set
TESTS["02_multiex_singletex"]="./materials/02_multiex_singletex/02_multiex_singletex.blend"

# 03_multiex_singletex_multimaterial
# export mul to multi, single tex set = each object has 1 tex set
# even if it has multiple materials
TESTS["03_multiex_singletex_multimaterial"]="./materials/03_multiex_singletex_multimaterial/03_multiex_singletex_multimaterial.blend"

# 04_singleex_multitex
# export mul to single, multi tex set = should be each material as own
TESTS["04_singleex_multitex"]="./materials/04_singleex_multitex/04_singleex_multitex.blend"

# 06_singleex_singletex
# export mul to single, multi tex set = All materials should be accounted for
TESTS["05_singleex_multitex_tradepaint"]="./materials/05_singleex_multitex_tradepaint/05_singleex_multitex_tradepaint.blend"

# 06_singleex_singletex
# export mul to single, single tex set = each object has 1 tex set
TESTS["06_singleex_singletex"]="./materials/06_singleex_singletex/06_singleex_singletex.blend"

# 07_07_singleex_singletex_tradepaint
# export mul to single, single tex set where both objects share materials
TESTS["07_singleex_singletex_tradepaint"]="./materials/07_singleex_singletex_tradepaint/07_singleex_singletex_tradepaint.blend"

# 08_multiex_multitex_instances
# export mul to multi, multi tex with instances put in map
TESTS["08_multiex_multitex_instances"]="./materials/08_multiex_multitex_instances/08_multiex_multitex_instances.blend"

# 09_singleex_singletex_instances
# export mul to single, single tex set with instances put in map
TESTS["09_singleex_singletex_instances"]="./materials/09_singleex_singletex_instances/09_singleex_singletex_instances.blend"

# 10_multiex_multitex_textured
# export mul to multi, multi tex set = should be each material as own
# including split objects
TESTS["10_multiex_multitex_textured"]="./materials/10_multiex_multitex_textured/10_multiex_multitex_textured.blend"

# 11_multiex_singletex_textured
# export mul to multi, single tex set = each object has 1 tex set
TESTS["11_multiex_singletex_textured"]="./materials/11_multiex_singletex_textured/11_multiex_singletex_textured.blend"

# 12_multiex_multitex_duplislots
# export mul to multi, multi tex with duplicate materials in slots
TESTS["12_multiex_multitex_duplislots"]="./materials/12_multiex_multitex_duplislots/12_multiex_multitex_duplislots.blend"

# 13_multiex_singletex_duplislots
# export mul to multi, single tex with duplicate materials in slots
TESTS["13_multiex_singletex_duplislots"]="./materials/13_multiex_singletex_duplislots/13_multiex_singletex_duplislots.blend"

# 14_singleex_multitex_duplislots
# export mul to single, multi tex with duplicate materials in slots
TESTS["14_singleex_multitex_duplislots"]="./materials/14_singleex_multitex_duplislots/14_singleex_multitex_duplislots.blend"

# 15_singleex_singletex_duplislots
# export mul to single, single tex with duplicate materials in slots
TESTS["15_singleex_singletex_duplislots"]="./materials/15_singleex_singletex_duplislots/15_singleex_singletex_duplislots.blend"

# 16_multiex_multitex_noslots
# One material has no slots
# including split objects
TESTS["16_multiex_multitex_noslots"]="./materials/16_multiex_multitex_noslots/16_multiex_multitex_noslots.blend"

# 17_multiex_customtex
TESTS["17_multiex_customtex"]="./materials/17_multiex_customtex/17_multiex_customtex.blend"

# Switch from multiex to singleex
TESTS["18_singleex_multitex_modeswitch"]="./materials/18_singleex_multitex_modeswitch/18_singleex_multitex_modeswitch.blend"

# Switch from multiex to singleex
TESTS["19_multiex_singletex_modeswitch"]="./materials/19_multiex_singletex_modeswitch/19_multiex_singletex_modeswitch.blend"

# Export entity with physics bodies
TESTS["20_singleex_singletex_entbodies"]="./export_files/20_singleex_singletex_entbodies/20_singleex_singletex_entbodies.blend"

# Export entity one object having no UVs and one having a full set
TESTS["21_multiex_multitex_uvsnoneandfull"]="./export_files/21_multiex_multitex_uvsnoneandfull/21_multiex_multitex_uvsnoneandfull.blend"

# Unusual characters in names
TESTS["22_multiex_multitex_characters"]="./export_files/22_multiex_multitex_characters/22_multiex_multitex_characters.blend"

# Light bake
TESTS["23_singleex_multitex_lightbake"]="./export_files/23_singleex_multitex_lightbake/23_singleex_multitex_lightbake.blend"

# Export rig
TESTS["24_singleex_multitex_rigging"]="./export_files/24_singleex_multitex_rigging/24_singleex_multitex_rigging.blend"

# Crash when exporting gargantuan leg
TESTS["25_multiex_multitex_syncdeletions"]="./export_files/25_multiex_multitex_syncdeletions/25_multiex_multitex_syncdeletions.blend"

# Plugging color into specular slot
TESTS["26_multiex_multitex_colorspec"]="./materials/26_multiex_multitex_colorspec/26_multiex_multitex_colorspec.blend"

# Suzanne mesh has no material slots
TESTS["27_multiex_singletex_noslots"]="./materials/27_multiex_singletex_noslots/27_multiex_singletex_noslots.blend"

# Use a very small texture with small texture fix disabled
TESTS["28_multiex_multitex_tinytexture"]="./materials/28_multiex_multitex_tinytexture/28_multiex_multitex_tinytexture.blend"



#===================================================
# If second argument is a valid test name
if [[ "$1" != "" ]] && [[ "$1" != "approve" ]]; then
    if [[ ${TESTS[$1]+_} ]]; then
        echo "-----"
        echo "Running test: $1"
        echo "-----"
        PREPFUNC=$($1)
        echo $PREPFUNC
        runTest ${TESTS[$1]} $2
        exit
    else
        echo "Not a valid test name"
        exit
    fi
else
    # Run all tests
    if [[ "$1" == "approve" ]]; then
        APPROVE="approve"
    fi
    for T in "${!TESTS[@]}"; do
        echo "-----"
        echo "Running ALL tests. Current: $T"
        echo "-----"
        PREPFUNC=$($T)
        echo $PREPFUNC
        runTest ${TESTS[$T]} $APPROVE
    done
    NC='\033[0m' # No Color
    GREEN='\033[0;32m'
    printf "${GREEN}ALL TESTS PASSED${NC}\n"
fi
