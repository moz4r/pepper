#!/bin/bash

# Reset PYTHONPATH (reason: on NAO, PYTHONPATH is set to a path with Python 2
# modules, notably qi, which won't work with Python 3, so we need to remove
# them. Use of PYTHONPATH is not recommended any more.)
export PYTHONPATH=""

# Add the directory containing python3 to PATH
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PATH="$SCRIPT_DIR:$PATH"

# fix 2.5
export LD_LIBRARY_PATH="/home/nao/opt/lib/libstdcpp:${LD_LIBRARY_PATH}"

# 2) Désactiver le user site-packages & pointer explicitement le site-packages Py3
export PYTHONNOUSERSITE=1
export PYTHONPATH="/home/nao/.local/share/PackageManager/apps/python3nao/lib/python3.9/site-packages"


# Check if any parameters were passed
if [ $# -eq 0 ]; then
  # No parameters passed, start Python REPL
  /home/nao/.local/share/PackageManager/apps/python3nao/bin/python3.9
else
  # Run the Python script
  /home/nao/.local/share/PackageManager/apps/python3nao/bin/python3.9 "$@"
fi;
