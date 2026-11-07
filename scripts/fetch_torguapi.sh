#!/bin/bash
# Download the torguapi Lambda layer and put its modules in ./torguapi, where
# the unit tests import them from. Needs AWS credentials that allow
# lambda:GetLayerVersion.
#
# Usage: scripts/fetch_torguapi.sh <layer arn without version> <version>
# e.g.   scripts/fetch_torguapi.sh arn:aws:lambda:us-east-1:490461464130:layer:layer_torguapi 7
set -euo pipefail

LAYER_ARN=${1:?usage: $0 <layer arn> <version>}
LAYER_VERSION=${2:?usage: $0 <layer arn> <version>}

URL=$(aws lambda get-layer-version \
          --layer-name "$LAYER_ARN" \
          --version-number "$LAYER_VERSION" \
          --query Content.Location \
          --output text)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -sSf "$URL" -o "$TMP/TorguapiLayer.zip"
unzip -qq -o "$TMP/TorguapiLayer.zip" 'python/*' -d "$TMP"

mkdir -p torguapi
find "$TMP/python/torguapi" -type f -exec mv {} torguapi/ \;
echo "torguapi layer v$LAYER_VERSION -> torguapi/"
