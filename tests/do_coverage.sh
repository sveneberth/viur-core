#!/usr/bin/env sh

set -ex

coverage run --source=../core -m unittest discover
coverage report
coverage html
python -m http.server 4242 -d htmlcov
