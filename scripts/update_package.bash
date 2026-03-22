#!/usr/bin/env bash

dist_dir="${1:?dist_dir argument is missing}"
package_json="${2:?package_json argument is missing}"
version="${3:?version argument is missing}"

which jq 1>/dev/null || { echo "jq dependency is missing"; exit 1; }

find "$dist_dir" -type f -printf '%P\n' | jq -Rn --arg version "${version}" '[inputs] |
    {
        version: $version,
        urls: map([., ("github:szeka9/PyRobusta/dist/" + .)]),
        deps: []
    }
' > $package_json
