import sys
import datetime
import json

import requests

from portingdb.load_data import get_data

PAGURE_URL = 'https://src.fedoraproject.org'
NOW = datetime.datetime.now()

data = get_data(*(sys.argv[1:] or ['data/']))

orphans = {
    n: p for n, p in data['packages'].items() if 'orphan' in p['maintainers']
}

info = {}

for i, package in enumerate(orphans):
    print(f'{i+1}/{len(orphans)} {package}', end=': ', file=sys.stderr)
    response = requests.get(f'{PAGURE_URL}/api/0/rpms/{package}')
    info[package] = response.json()
    date_modified = datetime.datetime.fromtimestamp(
        int(response.json()['date_modified'])
    )
    print(f'{(NOW - date_modified).days // 7} weeks', file=sys.stderr)

json.dump(info, sys.stdout, indent=2, sort_keys=True)
