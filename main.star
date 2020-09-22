# Copyright 2020 the V8 project authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

lucicfg.config(
    config_dir = "generated",
    tracked_files = [
        "cr-buildbucket.cfg",
        "project.cfg",
        "luci-logdog.cfg",
        "luci-milo.cfg",
        "luci-scheduler.cfg",
    ],
    fail_on_warnings = True,
)

luci.project(
    name = "wasm",
    buildbucket = "cr-buildbucket.appspot.com",
    logdog = "luci-logdog",
    milo = "luci-milo",
    notify = "luci-notify.appspot.com",
    scheduler = "luci-scheduler",
    swarming = "chromium-swarm.appspot.com",
    acls = [
        acl.entry(
            [
                acl.BUILDBUCKET_READER,
                acl.LOGDOG_READER,
                acl.PROJECT_CONFIGS_READER,
                acl.SCHEDULER_READER,
            ],
            groups = ["all"],
        ),
        acl.entry([acl.SCHEDULER_OWNER], groups = ["project-wasm-admins"]),
        acl.entry([acl.LOGDOG_WRITER], groups = ["luci-logdog-chromium-writers"]),
    ],
)

luci.logdog(
    gs_bucket = "chromium-luci-logdog",
)

luci.bucket(name = "ci", acls = [
    acl.entry(
        [acl.BUILDBUCKET_TRIGGERER],
        users = [
            "luci-scheduler@appspot.gserviceaccount.com",
        ],
    ),
])

def builder(name, os, category):
    goma_dict = {"server_host": "goma.chromium.org", "rpc_extra_params": "?prod"}
    if not os.startswith("Mac"):
        goma_dict["enable_ats"] = True
    luci.builder(
        name = name,
        bucket = "ci",
        executable = luci.recipe(
            name = "wasm_llvm",
            cipd_package = "infra/recipe_bundles/chromium.googlesource.com/chromium/tools/build",
            cipd_version = "refs/heads/master",
        ),
        swarming_tags = ["vpython:native-python-wrapper"],
        dimensions = {"cpu": "x86-64", "os": os, "pool": "luci.wasm.ci"},
        properties = {
            "$build/goma": goma_dict,
            "builder_group": "client.wasm.llvm",
        },
        execution_timeout = 14400 * time.second,
        build_numbers = True,
        service_account = "wasm-ci-builder@chops-service-accounts.iam.gserviceaccount.com",
        triggered_by = ["llvm-trigger"],
        triggering_policy = scheduler.policy(
            kind = scheduler.GREEDY_BATCHING_KIND,
            max_concurrent_invocations = 4,
        ),
    )
    luci.console_view_entry(
        console_view = "toolchain",
        builder = name,
        category = category,
        short_name = category,
    )

builder("linux", "Ubuntu-16.04", "Linux")
builder("mac", "Mac-10.13", "Mac")
builder("windows", "Windows-10", "Windows")

luci.milo(
    logo = "https://storage.googleapis.com/chrome-infra-public/logo/wasm.svg",
)

luci.console_view(
    name = "toolchain",
    title = "Toolchain",
    repo = "https://chromium.googlesource.com/external/github.com/llvm/llvm-project",
    refs = ["refs/heads/master"],
    favicon = "https://storage.googleapis.com/chrome-infra-public/logo/wasm.ico",
)

luci.gitiles_poller(
    name = "llvm-trigger",
    bucket = "ci",
    repo = "https://chromium.googlesource.com/external/github.com/llvm/llvm-project",
    refs = ["refs/heads/master"],
)
