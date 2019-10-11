#!/usr/bin/python3
import collections
import json

import dnf

cachedir = '_dnf_cache_dir'
the_arch = 'x86_64'

base = dnf.Base()
conf = base.conf
conf.cachedir = cachedir
conf.substitutions['releasever'] = '32'
conf.substitutions['basearch'] = the_arch

base.repos.add_new_repo('rawhide', conf,
    baseurl=["http://download.fedoraproject.org/pub/fedora/linux/development/rawhide//Everything/$basearch/os/"])
base.repos.add_new_repo('rawhide-source', conf,
    baseurl=["http://download.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/source/tree/"])
base.fill_sack(load_system_repo=False)

print("Enabled repositories:")
for repo in base.repos.iter_enabled():
    print("id: {}".format(repo.id))
    print("baseurl: {}".format(repo.baseurl))

class Cache:
    def __init__(self, key, func):
        self.cache = {}
        self.key = key
        self.func = func

    def __call__(self, item, parent, *args, **kwargs):
        key = self.key(item)
        try:
            result = self.cache[key]
        except KeyError:
            self.cache[key] = result = self.func(item, *args, **kwargs)
            result.parent = parent
            result.parents = []
        if parent is None:
            result.lineage = ()
        else:
            result.parents.append(parent)
            result.lineage = (parent, *parent.lineage)
        return result


def include_subpackage(name, all_names):
    if 'python3' in name and name.replace('python3', 'python2') in all_names:
        return False
    else:
        return True


class _SourcePackage:
    kind = 'SRC'

    def __init__(self, dnf_pkg):
        self.dnf_pkg = dnf_pkg
        self.name = dnf_pkg.name
        self.rpm_name = f'{dnf_pkg}.rpm'

    def expand(self):
        if self.name in (
            # Packages that only need python2 to build their python2 subpackages
            # (To be verified!)
            'boost',
            'protobuf',
            'qscintilla',
            'dbus-python',

            # These probably BR python2 by mistake (need investigation!)
            'lilv',
            'vtk',
        ):
            self.built_rpms = []
        else:
            q = base.sack.query().filter(sourcerpm=self.rpm_name)
            dnf_packages = [p for p in q if p.arch in (the_arch, 'noarch')]
            names = set(p.name for p in dnf_packages)
            self.built_rpms = [
                make_built_package(p, self) for p in dnf_packages
                if include_subpackage(p.name, names)
            ]
        return self.built_rpms

    def __str__(self):
        return f'SRC: {self.dnf_pkg.name} {self.dnf_pkg.arch}'

make_source_package = Cache(lambda p: p.name, _SourcePackage)

class _BuiltPackage:
    kind = 'BLT'

    def __init__(self, dnf_pkg):
        self.dnf_pkg = dnf_pkg
        self.name = dnf_pkg.name
        self.source_name = dnf_pkg.source_name

    def expand_src(self):
        q = base.sack.query().filter(name=self.dnf_pkg.source_name, arch='src')
        [self.source] = [make_source_package(p, self) for p in q]
        return [self.source]

    def expand(self):
        if self.source_name in (
            # Exceptions
            'chromium',
            'python-psutil',
            'mlt',
            'gimp',
            'gimp-layer-via-copy-cut',
            'gimp-resynthesizer',
            'pygobject2',
            'pygtk2',
            'pycairo',
            'postgresql',
            'pypy3',
            'pypy',
            'texlive-base',
            'qt5-qtwebengine',
            # Want exceptions for...
            'autodownloader',
            'mercurial',
            # Effectively removed:
            'dblatex',
            'bamf', 'bamf-devel',
        ):
            self.provides = []
        elif self.name in (
            # Temporary (to be replaced soon)
            'bzr',
        ):
            self.provides = []
        elif self.name.startswith('python3-'):
            self.provides = []
        else:
            self.provides = [
                make_provide(
                    p, self,
                    ignore_src=(
                        # Blanket build-only exception:
                        (self.source_name == 'python27')
                        # Temporary cuts (these are OK as build deps for now):
                        or (self.source_name == 'python2-setuptools')
                        or (self.source_name == 'python-docutils')
                        or (self.source_name == 'python-nose')
                        or (self.source_name == 'python-pytest')
                        or (self.source_name == 'epydoc')
                    ),
                )
                for p in self.dnf_pkg.provides
            ]
        return self.provides # + [self.source]

    def __str__(self):
        return f'BLT: {self.dnf_pkg.name} {self.dnf_pkg.arch}'

make_built_package = Cache(lambda p: p.name, _BuiltPackage)

def make_any_package(p, parent):
    if p.arch == 'src':
        return make_source_package(p, parent)
    else:
        return make_built_package(p, parent)

class _Provide:
    kind = 'DEP'

    def __init__(self, dnf_provide, ignore_src=False):
        self.dnf_provide = dnf_provide
        self.name = str(dnf_provide)
        self.ignore_src = ignore_src

    def expand(self):
        if self.name in (
            'font(:lang=en)',
        ):
            self.requirers = []
        else:
            q = base.sack.query().filter(requires=self.dnf_provide)
            self.requirers = [
                make_any_package(p, self) for p in q
                if not (self.ignore_src and p.arch == 'src')
            ]
        return self.requirers

    def __str__(self):
        return f'DEP: {self.dnf_provide} {"*" if self.ignore_src else ""}'

make_provide = Cache(lambda p: str(p), _Provide)

[python27_src] = base.sack.query().filter(name='python27', arch='src')

to_expand = collections.deque([make_source_package(python27_src, None)])
expanded = set()

def print_stats():
    done = len(expanded)
    todo = len(to_expand)
    print(
        f'{done}/{todo} ~{done/(done+todo):.0%}',
        f'provides={len(make_provide.cache)}',
        f'src={len(make_source_package.cache)}',
        f'built={len(make_built_package.cache)}',
    )

def ensure_expanded(item):
    if item in expanded:
        return
    expanded.add(item)
    print(item)
    for ancestor, nxt in zip(item.lineage, (*item.lineage[1:], None)):
        print(('`-', '|-')[bool(nxt)], ancestor)
    for child in item.expand():
        print('  ->', child)
        to_expand.append(child)

while to_expand:
    item = to_expand.popleft()
    ensure_expanded(item)
    print_stats()

if False:
    print('Adding Python 3')

    [python3_src] = base.sack.query().filter(name='python3', arch='src')
    item = make_source_package(python3_src, None)
    ensure_expanded(item)
    for item in list(to_expand):
        ensure_expanded(item)
    print_stats()


print('Shallowly expanding deps')

for item in list(to_expand):
    if item.kind == 'DEP':
        ensure_expanded(item)
print_stats()


print('Adding source RPMs')

for item in list(make_built_package.cache.values()):
    item.expand_src()
print_stats()

def get_ident(item):
    return f'{item.kind}:{item.name}'

with open('dep_graph.jsonlines', 'w') as f:
    for item in (
        *make_built_package.cache.values(),
        *make_source_package.cache.values(),
        *make_provide.cache.values(),
    ):
        print(json.dumps({
            'ident': get_ident(item),
            'name': item.name,
            'kind': item.kind,
            'depth': len(item.lineage),
            'parents': [get_ident(p) for p in item.parents],
        }), file=f)
