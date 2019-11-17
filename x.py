#!/usr/bin/env python3

from collections import namedtuple
from urllib import request
import os
import subprocess
import sys

rust_version = "1.39.0"
rustup_version = "1.20.2"

DebianArch = namedtuple("DebianArch", ["bashbrew", "dpkg", "rust"])

debian_arches = [
    DebianArch("amd64", "amd64", "x86_64-unknown-linux-gnu"),
    DebianArch("arm32v7", "armhf", "armv7-unknown-linux-gnueabihf"),
    DebianArch("arm64v8", "arm64", "aarch64-unknown-linux-gnu"),
    DebianArch("i386", "i386", "i686-unknown-linux-gnu"),
]

debian_variants = [
    "stretch",
    "buster",
]

default_debian_variant = "buster"

alpine_versions = [
    "3.10",
]

default_alpine_version = "3.10"

rustup_profiles = [
    "minimal",
    "default",
    "full",
]

def rustup_hash(arch):
    url = f"https://static.rust-lang.org/rustup/archive/{rustup_version}/{arch}/rustup-init.sha256"
    with request.urlopen(url) as f:
        return f.read().decode('utf-8').split()[0]

def read_file(file):
    with open(file, "r") as f:
        return f.read()

def write_file(file, contents):
    dir = os.path.dirname(file)
    if dir and not os.path.exists(dir):
        os.makedirs(dir)
    with open(file, "w") as f:
        f.write(contents)

def update_debian():
    arch_case = 'dpkgArch="$(dpkg --print-architecture)"; \\\n'
    arch_case += '    case "${dpkgArch##*-}" in \\\n'
    for arch in debian_arches:
        hash = rustup_hash(arch.rust)
        arch_case += f"        {arch.dpkg}) rustArch='{arch.rust}'; rustupSha256='{hash}' ;; \\\n"
    arch_case += '        *) echo >&2 "unsupported architecture: ${dpkgArch}"; exit 1 ;; \\\n'
    arch_case += '    esac'

    template = read_file("Dockerfile-debian.template")
    slim_template = read_file("Dockerfile-slim.template")

    for variant in debian_variants:
        for rustup_profile in rustup_profiles:
            rendered = template \
                .replace("%%RUST-VERSION%%", rust_version) \
                .replace("%%RUSTUP-VERSION%%", rustup_version) \
                .replace("%%DEBIAN-SUITE%%", variant) \
                .replace("%%ARCH-CASE%%", arch_case) \
                .replace("%%RUSTUP-PROFILE%%", rustup_profile)
            write_file(f"{rust_version}/{variant}-{rustup_profile}/Dockerfile", rendered)

            rendered = slim_template \
                .replace("%%RUST-VERSION%%", rust_version) \
                .replace("%%RUSTUP-VERSION%%", rustup_version) \
                .replace("%%DEBIAN-SUITE%%", variant) \
                .replace("%%ARCH-CASE%%", arch_case) \
                .replace("%%RUSTUP-PROFILE%%", rustup_profile)
            write_file(f"{rust_version}/{variant}-{rustup_profile}/slim/Dockerfile", rendered)

def update_alpine():
    template = read_file("Dockerfile-alpine.template")

    for version in alpine_versions:
        for rustup_profile in rustup_profiles:
            rendered = template \
                .replace("%%RUST-VERSION%%", rust_version) \
                .replace("%%RUSTUP-VERSION%%", rustup_version) \
                .replace("%%TAG%%", version) \
                .replace("%%RUSTUP-SHA256%%", rustup_hash("x86_64-unknown-linux-musl")) \
                .replace("%%RUSTUP-PROFILE%%", rustup_profile)
            write_file(f"{rust_version}/alpine{version}-{rustup_profile}/Dockerfile", rendered)

def update_travis():
    file = ".travis.yml"
    config = read_file(file)

    versions = ""
    for variant in debian_variants:
        for rustup_profile in rustup_profiles:
            versions += f"  - VERSION={rust_version} VARIANT={variant}-{rustup_profile}\n"
            versions += f"  - VERSION={rust_version} VARIANT={variant}-{rustup_profile}/slim\n"

    for version in alpine_versions:
        for rustup_profile in rustup_profiles:
            versions += f"  - VERSION={rust_version} VARIANT=alpine{version}-{rustup_profile}\n"

    marker = "#VERSIONS\n"
    split = config.split(marker)
    rendered = split[0] + marker + versions + marker + split[2]
    write_file(file, rendered)

def file_commit(file):
    return subprocess.run(
            ["git", "log", "-1", "--format=%H", "HEAD", "--", file],
            capture_output = True) \
        .stdout \
        .decode('utf-8') \
        .strip()

def version_tags():
    parts = rust_version.split(".")
    tags = []
    for i in range(len(parts)):
        tags.append(".".join(parts[:i + 1]))
    return tags

def single_library(tags, architectures, dir):
    return f"""
Tags: {", ".join(tags)}
Architectures: {", ".join(architectures)}
GitCommit: {file_commit(os.path.join(dir, "Dockerfile"))}
Directory: {dir}
"""

def generate_stackbrew_library():
    commit = file_commit("x.py")

    library = f"""\
# this file is generated via https://github.com/rust-lang-nursery/docker-rust/blob/{commit}/x.py

Maintainers: Steven Fackler <sfackler@gmail.com> (@sfackler)
GitRepo: https://github.com/rust-lang-nursery/docker-rust.git
"""

    for variant in debian_variants:
        for rustup_profile in rustup_profiles:
            tags = []
            for version_tag in version_tags():
                tags.append(f"{version_tag}-{variant}-{rustup_profile}")
            tags.append(f"{variant}-{rustup_profile}")
            if variant == default_debian_variant:
                for version_tag in version_tags():
                    tags.append(f"version_tag-{rustup_profile}")
                tags.append(f"latest-{rustup_profile}")

            library += single_library(
                    tags,
                    map(lambda a: a.bashbrew, debian_arches),
                    os.path.join(rust_version, variant))

            tags = []
            for version_tag in version_tags():
                tags.append(f"{version_tag}-slim-{variant}-{rustup_profile}")
            tags.append(f"slim-{variant}-{rustup_profile}")
            if variant == default_debian_variant:
                for version_tag in version_tags():
                    tags.append(f"{version_tag}-slim-{rustup_profile}")
                tags.append(f"slim-{rustup_profile}")

            library += single_library(
                    tags,
                    map(lambda a: a.bashbrew, debian_arches),
                    os.path.join(rust_version, f"{variant}-{rustup_profile}", "slim"))

    for version in alpine_versions:
        for rustup_profile in rustup_profiles:
            tags = []
            for version_tag in version_tags():
                tags.append(f"{version_tag}-alpine{version}-{rustup_profile}")
            tags.append(f"alpine{version}-{rustup_profile}")
            if version == default_alpine_version:
                for version_tag in version_tags():
                    tags.append(f"{version_tag}-alpine-{rustup_profile}")
                tags.append(f"alpine-{rustup_profile}")

            library += single_library(
                tags,
                ["amd64"],
                os.path.join(rust_version, f"alpine{version}-{rustup_profile}"))

    print(library)

def usage():
    print(f"Usage: {sys.argv[0]} update|generate-stackbrew-library")
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        usage()

    task = sys.argv[1]
    if task == "update":
        update_debian()
        update_alpine()
        update_travis()
    elif task == "generate-stackbrew-library":
        generate_stackbrew_library()
    else:
        usage()
