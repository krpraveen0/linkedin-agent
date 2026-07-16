#!/usr/bin/env bash
set -euo pipefail

python3 aep/pipelines/run_pipeline.py --mode morning
python3 aep/pipelines/validate_artifacts.py --mode morning

echo "AEP morning pipeline completed"
