#!/bin/bash

python3 -m venv unit-test-generator-venv

source unit-test-generator-venv/bin/activate

pip install -r requirements.txt

pyinstaller --onefile generate_unit_tests.py