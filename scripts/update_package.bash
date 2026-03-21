#!/usr/bin/env bash

dist_dir="${1:?dist_dir parameter is missing}"
package_json="${2:?package_json parameter is missing}"

which jq || { echo "jq dependency is missing"; exit 1; }

find "$dist_dir" -type f -printf '%P\n' | jq -Rn '[inputs] |
    {
        version: "0.2",
        urls: map([., ("github:szeka9/PyRobusta/dist/" + .)]),
        deps: []
    }
' > $package_json
