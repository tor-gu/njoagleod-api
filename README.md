
# njoagleod-api

This is the source code for the NJ OAG Law Enforcement Officer Diversity
API deployed at `api.tor-gu.com/nj/officer_diversity/`.

It serves [njoagleod](https://github.com/tor-gu/njoagleod), a cleaned-up
copy of the NJ Attorney General’s [Law Enforcement Officer
Diversity](https://www.njoag.gov/policerecruiting/) data: officers for
2021 to 2025, and applicants and agency hiring and promotion practices
for 2022 to 2025. Field names and values are the same as in the R
package; see it for more details on the underlying dataset.

## Try it out

### OpenAPI/Swagger

There is an OpenAPI/swagger document deployed
[here](https://tor-gu.com/apis/njoagleod.html) that you can play with.
The spec is `officer-diversity-openapi.yaml`.

### Endpoints

All under `/nj/officer_diversity`:

| Endpoint                               | R equivalent                                  | Filters                            |
|----------------------------------------|-----------------------------------------------|------------------------------------|
| `/officers`                            | the `officer` table                           | every column but `officer_count`   |
| `/applicants`                          | the `applicant` table                         | every column but `applicant_count` |
| `/counts/officers?by=`                 | `count(officer, ..., wt = officer_count)`     | as `/officers`                     |
| `/counts/applicants?by=`               | `count(applicant, ..., wt = applicant_count)` | as `/applicants`                   |
| `/agency_practices`                    | the `agency_practice` table                   | every column                       |
| `/agency_practices/{year}/{agency_id}` | one row of `agency_practice`                  |                                    |

`/officers` and `/applicants` are count tables: each row is a
combination of year, agency and characteristics, with the number of
people who share it. **Counting rows counts combinations, not people**,
so use `/counts/*` or sum the count field. `by` takes 1 to 4 columns,
comma-separated.

### Sample code

Each endpoint returns paginated results, with a `"next"` url in the
`"links"` section indicating that there are more results to be
retrieved.

This is illustrated in the python code below, which loads the number of
officers by year and race into a [pandas
DataFrame](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html).

``` python
import json
import requests
import pandas as pd

API_ROOT = r.API_ROOT
DIVERSITY = f"{API_ROOT}/nj/officer_diversity"


def load_as_df(url):
    """Retrieve entire dataset at url and return as a dataframe"""
    # Get the first page
    resp = requests.get(url)
    resp.raise_for_status()
    resp_json = json.loads(resp.content.decode('utf-8'))
    df = pd.DataFrame(resp_json["data"])

    # Keep retrieving pages while there is a 'next' link
    while "next" in resp_json["links"]:
        resp = requests.get(resp_json["links"]["next"])
        resp.raise_for_status()
        resp_json = json.loads(resp.content.decode('utf-8'))
        df = pd.concat([df, pd.DataFrame(resp_json["data"])], ignore_index=True)
    return df


by_race = load_as_df(f"{DIVERSITY}/counts/officers?by=year,officer_race")
by_race_wide = (by_race.assign(officer_race=by_race["officer_race"].fillna("(not reported)"))
                .pivot(index="officer_race", columns="year", values="count")
                .rename(columns=str).reset_index())
```

| officer_race                              |  2021 |  2022 |  2023 |  2024 |  2025 |
|:------------------------------------------|------:|------:|------:|------:|------:|
| (not reported)                            |   205 |   266 |   348 |   453 |   284 |
| American Indian or Alaska Native          |    24 |    28 |    34 |    29 |    32 |
| Asian                                     |   477 |   498 |   533 |   555 |   575 |
| Black or African American                 |  2898 |  2933 |  3048 |  2797 |  3092 |
| Hispanic                                  |  5382 |  5693 |  6036 |  6061 |  6360 |
| Native Hawaiian or other Pacific Islander |    48 |    57 |    62 |    54 |    68 |
| Other                                     |   127 |   159 |   201 |   182 |   138 |
| Two or more races                         |   149 |   162 |   177 |   210 |   204 |
| White                                     | 21337 | 21271 | 20864 | 21286 | 20785 |

#### Agency names

Records carry `agency_id` only. Names, counties and the rest come from
the [njlea API](https://tor-gu.com/apis/njlea.html), joined on
`agency_id`. Here are the ten largest agencies of 2025, with their share
of female officers:

``` python
officers_2025 = load_as_df(f"{DIVERSITY}/counts/officers?by=agency_id,officer_gender&year=2025")
agencies_2025 = load_as_df(f"{API_ROOT}/nj/lea/agencies/2025")

totals = officers_2025.groupby("agency_id")["count"].sum().rename("officers")
female = (officers_2025[officers_2025["officer_gender"] == "Female"]
          .set_index("agency_id")["count"].rename("female"))
largest = (pd.concat([totals, female], axis=1).fillna({"female": 0}).reset_index()
           .assign(pct_female=lambda d: (100 * d["female"] / d["officers"]).round(1))
           .merge(agencies_2025[["agency_id", "agency_name", "county"]], on="agency_id")
           .nlargest(10, "officers")
           [["agency_name", "county", "officers", "pct_female"]])
```

| agency_name                         | county         | officers | pct_female |
|:------------------------------------|:---------------|---------:|-----------:|
| New Jersey State Police             | NA             |     3351 |        5.3 |
| Newark Police Department            | Essex County   |     1105 |       23.4 |
| Jersey City Police Department       | Hudson County  |      797 |       17.9 |
| Paterson Police Department          | Passaic County |      406 |       16.0 |
| Essex County Sheriff’s Office       | Essex County   |      370 |       22.2 |
| Passaic County Sheriff’s Office     | Passaic County |      363 |       11.8 |
| Camden County Police Department     | Camden County  |      353 |       12.5 |
| Elizabeth Police Department         | Union County   |      335 |       13.7 |
| New Jersey Youth Justice Commission | NA             |      325 |       14.8 |
| Hudson County Sheriff’s Office      | Hudson County  |      309 |       17.5 |

#### Applicants

`/counts/applicants` works the same way. Here are the outcomes of
applications by year:

``` python
outcomes = load_as_df(f"{DIVERSITY}/counts/applicants?by=year,outcome")
outcomes_wide = (outcomes.assign(outcome=outcomes["outcome"].fillna("(not reported)"))
                 .pivot(index="outcome", columns="year", values="count")
                 .rename(columns=str).reset_index())
```

| outcome             |  2022 |  2023 |  2024 |  2025 |
|:--------------------|------:|------:|------:|------:|
| (not reported)      |    67 |    50 |   411 |  1536 |
| Appointed to Agency |  2130 |  2525 |  2343 |  2307 |
| Not Appointed       | 16178 | 16797 | 18528 | 20145 |
| Pending             |  3239 |  3019 |  2864 |  4729 |

#### Agency practices

`/agency_practices` has each agency’s answers about how it hires and
promotes officers. Every answer is also a filter, so `meta.record_count`
says how many agencies gave it:

``` python
url = f"{DIVERSITY}/agency_practices?year=2025&hiring_civil_service=true&page_size=1"
civil_service_agencies = requests.get(url).json()["meta"]["record_count"]
```

    202 agencies report that Civil Service governs their hiring in 2025.

#### Use of force

The `agency_id` is the same one
[njoaguof-api](https://tor-gu.com/apis/njoaguof.html) uses, so
use-of-force incidents can be set against the size of each agency’s
force. Here are 2024 incidents per 100 officers, by number of officers.
Incidents of agencies with no officers in this data are left out.

``` python
officers_2024 = load_as_df(f"{DIVERSITY}/counts/officers?by=agency_id&year=2024")
incidents_2024 = load_as_df(f"{API_ROOT}/nj/use_of_force/counts/incidents?by=agency_id&year=2024")

rates = (officers_2024.rename(columns={"count": "officers"})
         .merge(incidents_2024.rename(columns={"count": "incidents"}), on="agency_id", how="left")
         .fillna({"incidents": 0})
         .assign(size=lambda d: pd.cut(d["officers"], [0, 25, 100, 500, 100000],
                                       labels=["1-25", "26-100", "101-500", "over 500"])))
by_size = (rates.groupby("size", observed=True)
           .agg(agencies=("agency_id", "size"), officers=("officers", "sum"),
                incidents=("incidents", "sum"))
           .astype({"incidents": int})
           .assign(incidents_per_100=lambda d: (100 * d["incidents"] / d["officers"]).round(1))
           .reset_index())
by_size["size"] = by_size["size"].astype(str)
```

| size     | agencies | officers | incidents | incidents_per_100 |
|:---------|---------:|---------:|----------:|------------------:|
| 1-25     |      214 |     3511 |      1718 |              48.9 |
| 26-100   |      244 |    11806 |      7446 |              63.1 |
| 101-500  |       64 |    11141 |      7451 |              66.9 |
| over 500 |        3 |     5169 |      2993 |              57.9 |

#### Caveats

The data is as reported by each agency, and some agency-years look
incomplete. Nothing is corrected. Lakewood PD, for example, reports far
fewer officers in 2022 and 2025:

``` python
lakewood = load_as_df(f"{DIVERSITY}/counts/officers?by=year&agency_id=NJLEA0401")
```

| year | count |
|-----:|------:|
| 2021 |   153 |
| 2022 |    20 |
| 2023 |   162 |
| 2024 |   173 |
| 2025 |    58 |

The promotion columns are almost entirely `null` in 2021, so don’t read
`null` as “no”:

``` python
promoted = load_as_df(f"{DIVERSITY}/counts/officers?by=year,promoted")
promoted_wide = (promoted.assign(promoted=promoted["promoted"].map(
                     {True: "true", False: "false"}).fillna("null"))
                 .pivot(index="year", columns="promoted", values="count")
                 .reset_index())
```

| year | false |  null | true |
|-----:|------:|------:|-----:|
| 2021 |    28 | 30617 |    2 |
| 2022 | 20704 |  8069 | 2294 |
| 2023 | 21098 |  8162 | 2043 |
| 2024 | 25197 |  4261 | 2169 |
| 2025 | 25502 |  3765 | 2271 |

## Deploying

This API is implemented as an [AWS
SAM](https://aws.amazon.com/serverless/sam/) application: one Lambda
function serves every route, with the data packaged in it. A deployment
has three parts:

1.  The lambda layer
    [layer_torguapi](https://github.com/tor-gu/layer_torguapi) (version
    11 or later), which needs to be deployed separately.
2.  The data: CSV exports of a tagged
    [njoagleod](https://github.com/tor-gu/njoagleod) release, committed
    in `data/`, and built into `diversity/data/` by `make data`.
3.  The Lambda and API Gateway, defined in `template.yaml`.

### Data

`data/` holds the njoagleod tables and `SOURCE`, which records the
release they were exported from. The export also writes R’s own
`dplyr::count()` results to `tests/parity/expected/`, which the parity
test requires the API to reproduce, along with the tables themselves. To
export a release (this needs R and the `remotes` package; the release is
installed into a temporary library) and build the Lambda’s data:

    make export_data REF=v2.0.0
    make data

`diversity/data/` holds one file of int32s per column and `labels.json`,
so a request loads only the columns it uses. It is not committed; CI
builds it with `make data` before testing and before `sam build`.

### Data update

1.  `make export_data REF=<new release>`, and review the diff in
    `data/`.
2.  `make data parity_test example_test`. The spec’s examples, its enums
    and years, and this README (then `make knit`) may need updating; the
    example test shows the new values.
3.  Push to `dev`, check the dev API, then merge to `main`.

### Development

    make venv          # .venv with the test, style and spec tools
    make style unit_test
    make data example_test parity_test
    make apigateway_spec   # the spec for API Gateway, without examples

The unit tests import the torguapi layer from `./torguapi`;
`scripts/fetch_torguapi.sh` downloads it.

### Direct deploy

The application can be deployed directly using the SAM CLI:

    make data apigateway_spec
    sam build
    sam deploy --stack-name MyStackName                                                         \
               --capabilities CAPABILITY_IAM                                                    \
               --resolve-s3                                                                     \
               --parameter-overrides                                                            \
                    TorguapiLayerArn=arn:aws:lambda:us-east-1:123456789012:layer:layer_torguapi \
                    TorguapiLayerVersion=11                                                     \
                    ApiRoot=https://api.example.com                                             \
                    DataVersion=$(sed -n 's/^version=//p' data/SOURCE)

Replace the `TorguapiLayerXXX` params with the values derived from the
`layer_torguapi` deployment.

The `ApiRoot` value is used only for generating the values in `"links"`
in the JSON reply. On `api.tor-gu.com`, the relationship between the
publicly facing API URL and the API Gateway endpoints is configured in
[torgu-api-cloudfront](https://github.com/tor-gu/torgu-api-cloudfront).

To deploy a second environment alongside the first, give it a resource
name prefix (I use `dev-`) with the `EnvPrefix` template parameter.

### Using GitHub Actions

`.github/workflows/deploy.yml` deploys from GitHub: a push to `dev`
deploys the dev stack and runs the integration tests against it, and a
merge to `main` deploys prod. It assumes AWS roles through GitHub’s OIDC
provider; the roles are defined in `infra/github/` (Terraform).
