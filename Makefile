export AWS_SAM_STACK_NAME ?= NjoagleodApiDev

# The local venv when there is one (make venv); CI has none and uses python
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

src_dirs := diversity scripts tests

style:
	$(PYTHON) -m isort --profile black $(src_dirs)
	$(PYTHON) -m black --target-version py312 $(src_dirs)
	$(PYTHON) -m flake8 --ignore E501,E203,W503 $(src_dirs)

unit_test:
	$(PYTHON) -m pytest -sv tests/unit

# The spec's example replies, reproduced from the full data (needs make data)
example_test:
	$(PYTHON) -m pytest -sv tests/examples

# R's tables and counts (data/, tests/parity/expected), reproduced by the handler
# (needs make data)
parity_test:
	$(PYTHON) -m pytest -sv tests/parity

integration_test:
	$(PYTHON) -m pytest -sv tests/integration

# The local venv (.venv, Python 3.12 as in CI and on Lambda)
venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

# Export the njoagleod tables from a tagged release, e.g. make export_data REF=v2.0.0
export_data:
	@test -n "$(REF)" || (echo "Usage: make export_data REF=<njoagleod git ref>" && exit 1)
	Rscript scripts/export_data.R $(REF)

# Build the function's data (diversity/data/) from data/
data:
	$(PYTHON) scripts/build_data.py data .

# README.md from README.Rmd. Its python chunks call the live API (NJOAGLEOD_API_ROOT,
# default https://api.tor-gu.com) through reticulate and need requests and pandas;
# use the repo's virtualenv for them if there is one
ifneq ($(wildcard .venv/bin/python),)
knit: export RETICULATE_PYTHON ?= $(abspath .venv/bin/python)
endif
knit:
	Rscript -e "rmarkdown::render('README.Rmd')"

# The spec as template.yaml gives it to API Gateway (without examples)
apigateway_spec:
	$(PYTHON) scripts/apigateway_spec.py officer-diversity-openapi.yaml apigateway-openapi.yaml

.PHONY: venv style unit_test example_test parity_test integration_test knit export_data data apigateway_spec

all: style unit_test data example_test parity_test
