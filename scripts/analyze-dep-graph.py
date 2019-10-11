import datetime
import collections
import itertools
import json

from portingdb.load_data import get_data

PY2_IDENTS = {
    'SRC:python27',
    'BLT:python27',
    'DEP:python(abi) = 2.7',
}

now = datetime.datetime.now()

data = get_data('data/')

def make_item(jsonline):
    item = json.loads(jsonline)
    if item['ident'] in PY2_IDENTS:
        item['depth'] = 0
    return item['ident'], item

with open('dep_graph.jsonlines') as f:
    info = dict(make_item(p) for p in f.readlines())

with open('data/pagure_owner_alias.json') as f:
    owners_info = json.load(f)

with open('data/orphans.json') as f:
    orphans_info = {n: datetime.datetime.fromisoformat(d) for n, d in json.load(f).items()}

def q(name):
    return '"' + name.replace('"', r'\"') + '"'

def yield_components(name, memo=None):
    if memo is None:
        memo = set()
    if name in memo:
        return
    memo.add(name)
    item = info[name]
    if item['kind'] == 'SRC':
        yield name
    else:
        for p in item['parents']:
            yield from yield_components(p, memo)

if False:
    print('digraph G {')
    for name, item in info.items():
        if item['kind'] == 'SRC':
            for comp in set().union(*(
                    yield_components(parent) for parent in item['parents']
            )):
                if comp != 'SRC:python27' and comp != name:
                    print(f'{q(name)} -> {q(comp)};')
    print('}')

# Assign maintainers

maintainer_packages = {}
for ident, item in sorted(info.items()):
    if item['kind'] == 'SRC':
        name = item['name']
        item['maintainers'] = owners_info['rpms'].get(name, ['UNKNOWN'])
        for maint in item['maintainers']:
            maintainer_packages.setdefault(maint, []).append(name)

class ReportLine:
    def __init__(self, ident, parent):
        self.ident = ident
        self.item = info[ident]
        self.kind = self.item['kind']
        self.name = self.item['name']
        self.label = self.item['name'].partition(' = ')[0]
        self.parent = parent
        self.is_py2 = (
            self.ident in PY2_IDENTS
            #or self.name.startswith('python2-')
            or self.ident.startswith('DEP:python2-devel =')
            or self.ident.startswith('DEP:python2 =')
            or self.ident.startswith('DEP:python2(x86_64) =')
        )
        self.number = -1

    def assign_number(self, counter):
        self.number = next(counter)
        for child in self.children:
            child.assign_number(counter)

    def print_out(self, indent=0, lineage=()):
        if self.ident in {l.ident for l in lineage}:
            return
        relationship = getattr(self.parent, 'kind', 'TOP'), self.kind
        if relationship == ('DEP', 'BLT') and self.parent.label == self.label:
            # dependency trivially provided by package
            for child in self.children:
                child.print_out(indent, (self, *lineage))
            return
        if relationship == ('SRC', 'BLT') and self.parent.label == self.label:
            # built package of the same name
            for child in self.children:
                child.print_out(indent, (self, *lineage))
            return
        if relationship == ('BLT', 'SRC') and self.parent.label == self.label:
            # component of the same name
            for child in self.children:
                child.print_out(indent, (self, *lineage))
            return
        rel_text = {
            ('TOP', 'SRC'): '',
            ('SRC', 'BLT'): 'which contains ',
            ('SRC', 'DEP'): 'which buildrequires ',
            ('BLT', 'DEP'): 'which requires ',
            ('BLT', 'SRC'): 'part of component ',
            ('DEP', 'BLT'): 'provided by ',
        }[relationship]
        debug = '' # "-".join(relationship)
        print(f'{"  "*indent}- {debug}{rel_text}{self.name}', end='')
        if self.elsewhere:
            if self.elsewhere.number == self.number:
                print(' (see elsewhere)', end='')
            elif self.elsewhere.number > self.number:
                print(' (see below)', end='')
            else:
                print(' (see above)', end='')
        elif self.kind == 'SRC':
            if 'orphan' in self.item['maintainers']:
                print(' (orphaned', end='')
                if name in orphans_info:
                    print(f' for {(now - orphans_info[name]).days} days', end='')
                print(')', end='')
        print()
        for child in self.children:
            child.print_out(indent+1, (self, *lineage))

    def expand(self, memo):
        self.elsewhere = None
        if self.is_py2:
            self.children = []
            return
        parent_idents = set(self.item['parents'])
        if (
            self.name.startswith('python2-')
            and any(p in PY2_IDENTS for p in parent_idents)
        ):
            self.children = []
            return
        self.elsewhere = memo.get(self.ident)
        if self.elsewhere:
            self.children = []
            return
        memo[self.ident] = self
        self.expanded = True
        min_depth = min(info[p]['depth'] for p in parent_idents)
        self.children = [
            ReportLine(p, self) for p in sorted(parent_idents)
            if info[p]['depth'] == min_depth
        ]
        yield from self.children

for maintainer in sorted(
    maintainer_packages,
    #key=lambda k: (len(maintainer_packages[k]) < 10, len(maintainer_packages[k]))
):
    pkgs = maintainer_packages[maintainer]
    print()
    print('###')
    print()
    s = 's' if len(pkgs) > 1 else ''
    if maintainer == 'orphan':
        print(f'To whom it may concern,')
        print(f'{len(pkgs)} orphaned package{s} may be removed as we drop Python 2 from Fedora.')
    else:
        print(f'Dear {maintainer},')
        print(f'You maintain {len(pkgs)} package{s} that may be removed as we drop Python 2 from Fedora.') 
    print('Please remove Python 2 related dependencies, or coordinate with the (co)-maintainers of packages below.')
    print()

    if s:
        print('These are:')
    else:
        print('The package is:')
    lines = [ReportLine('SRC:' + p, None) for p in sorted(pkgs)]
    memo = {}
    to_expand = collections.deque(lines)
    while to_expand:
        line = to_expand.popleft()
        to_expand.extend(line.expand(memo))
    counter = itertools.count()
    for line in lines:
        line.assign_number(counter)
    for line in lines:
        line.print_out()

    continue
    print()
    print(f'Please note:')
    print(f"- Please reply if you need any more info, or any help. We won't touch your package (unless it would unbreak things we care about), but we can help if you ask.")
    print(f'- The summary above is generated semi-automatically, and might be somewhat confusing.')
    print(f"- If this is spam, we're sorry. Please fix the packages.")

print(f'\n###\n\n{len(maintainer_packages)} mails generated')
print(f'TODO:')
print(f'- link to open bugs')
print(f'- filter out FESCo exceptions')
print(f'- filter out python-module-only packages')
print(f'- filter out python SIG packages')
print(f'- filter out active maintainers?')
