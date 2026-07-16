#!/usr/bin/env bash
set -euo pipefail

bash aep/pipelines/morning-orchestrator.sh
bash aep/pipelines/evening-orchestrator.sh

python3 aep/pipelines/validate_artifacts.py --mode morning
python3 aep/pipelines/validate_artifacts.py --mode evening

echo "AEP smoke test passed"
