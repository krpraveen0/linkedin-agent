#!/usr/bin/env bash
set -euo pipefail

python3 aep/pipelines/run_pipeline.py --mode evening
python3 aep/pipelines/validate_artifacts.py --mode evening

echo "AEP evening pipeline completed"
