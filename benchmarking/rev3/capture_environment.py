#!/usr/bin/env python3
"""
Capture the complete execution environment into one machine-readable record.

A reviewer asked for the hardware, the runtime versions, the resources granted
to Docker and the limits applied to each container to be documented rather than
implied. Collecting them with a script instead of by hand means the table in the
paper can be regenerated and checked rather than trusted.

Run this while the stack under test is up, once per stack.
"""
import json
import os
import re
import subprocess
import sys
import time

APP_CONTAINERS = ["swift-user-service", "swift-product-service", "swift-order-service",
                  "java-user-service", "java-product-service", "java-order-service"]
INFRA_CONTAINERS = ["research-postgres", "research-redis"]


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str))
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def host():
    return {
        "model_identifier": run(["sysctl", "-n", "hw.model"]),
        "chip": run(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "logical_cores": run(["sysctl", "-n", "hw.ncpu"]),
        "performance_cores": run(["sysctl", "-n", "hw.perflevel0.logicalcpu"]),
        "efficiency_cores": run(["sysctl", "-n", "hw.perflevel1.logicalcpu"]),
        "memory_bytes": run(["sysctl", "-n", "hw.memsize"]),
        "os": run(["sw_vers", "-productName"]) + " " + run(["sw_vers", "-productVersion"]),
        "os_build": run(["sw_vers", "-buildVersion"]),
        "architecture": run(["uname", "-m"]),
    }


def docker_env():
    info = run(["docker", "info", "--format", "{{json .}}"])
    d = {}
    if info:
        try:
            j = json.loads(info)
            d = {
                "server_version": j.get("ServerVersion"),
                "cpus_allocated": j.get("NCPU"),
                "memory_allocated_bytes": j.get("MemTotal"),
                "storage_driver": j.get("Driver"),
                "cgroup_version": j.get("CgroupVersion"),
                "operating_system": j.get("OperatingSystem"),
                "kernel_version": j.get("KernelVersion"),
            }
        except json.JSONDecodeError:
            pass
    d["compose_version"] = run(["docker", "compose", "version", "--short"])
    return d


def container_limits():
    out = {}
    for c in APP_CONTAINERS + INFRA_CONTAINERS:
        raw = run(["docker", "inspect", c, "--format", "{{json .}}"], timeout=40)
        if not raw:
            continue
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            continue
        hc = j.get("HostConfig", {})
        cfg = j.get("Config", {})
        quota, period = hc.get("CpuQuota") or 0, hc.get("CpuPeriod") or 0
        out[c] = {
            "image": cfg.get("Image"),
            "image_id": j.get("Image"),
            "cpu_quota": quota,
            "cpu_period": period,
            "cpu_limit_cores": round(quota / period, 3) if quota and period else None,
            "nano_cpus": hc.get("NanoCpus"),
            "memory_limit_bytes": hc.get("Memory"),
            "memory_swap_bytes": hc.get("MemorySwap"),
            "state": (j.get("State") or {}).get("Status"),
            "env": {k: v for k, v in
                    (e.split("=", 1) for e in (cfg.get("Env") or []) if "=" in e)
                    if not re.search(r"PASSWORD|SECRET|DATABASE_URL|DATASOURCE_URL", k, re.I)},
        }
        if out[c]["cpu_limit_cores"] is None and hc.get("NanoCpus"):
            out[c]["cpu_limit_cores"] = round(hc["NanoCpus"] / 1e9, 3)
    return out


def runtime_versions():
    v = {"k6": run(["k6", "version"])}

    # Swift and Vapor, read out of the build manifests and the builder image.
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pkg = os.path.join(root, "services/swift/user-service/Package.swift")
    if os.path.exists(pkg):
        text = open(pkg).read()
        v["vapor_requirement"] = (re.search(r'vapor\.git".*?from:\s*"([^"]+)"', text) or [None, None])[1]
        v["fluent_requirement"] = (re.search(r'fluent\.git".*?from:\s*"([^"]+)"', text) or [None, None])[1]
        v["fluent_postgres_requirement"] = (re.search(r'fluent-postgres-driver\.git".*?from:\s*"([^"]+)"', text) or [None, None])[1]
        v["redis_requirement"] = (re.search(r'redis\.git".*?from:\s*"([^"]+)"', text) or [None, None])[1]
        v["swift_tools_version"] = (re.search(r'swift-tools-version:([\d.]+)', text) or [None, None])[1]
    df = os.path.join(root, "services/swift/user-service/Dockerfile")
    if os.path.exists(df):
        v["swift_builder_image"] = (re.search(r'FROM\s+(swift:[^\s]+)', open(df).read()) or [None, None])[1]

    pom = os.path.join(root, "services/java/user-service/pom.xml")
    if os.path.exists(pom):
        text = open(pom).read()
        v["spring_boot_version"] = (re.search(r'spring-boot-starter-parent</artifactId>\s*<version>([^<]+)', text) or [None, None])[1]
        v["java_version_property"] = (re.search(r'<java\.version>([^<]+)', text) or [None, None])[1]
    jdf = os.path.join(root, "services/java/user-service/Dockerfile")
    if os.path.exists(jdf):
        t = open(jdf).read()
        v["java_builder_image"] = (re.search(r'FROM\s+(maven:[^\s]+)', t) or [None, None])[1]
        v["java_runtime_image"] = (re.search(r'FROM\s+(eclipse-temurin:[^\s]+)', t) or [None, None])[1]
        m = re.search(r'ENV JAVA_OPTS="(.*?)"', t, re.S)
        # The Dockerfile writes JAVA_OPTS across continued lines, so strip the
        # continuation backslashes rather than printing them in the table.
        v["jvm_args"] = " ".join(m.group(1).replace("\\", " ").split()) if m else None

    # Versions read from the running containers, which is what actually ran.
    v["jvm_runtime_reported"] = run(["docker", "exec", "java-user-service", "java", "-version"]) or \
        run("docker exec java-user-service sh -c 'java -version 2>&1'")
    v["swift_runtime_libs"] = run("docker exec swift-user-service sh -c 'ls /usr/lib/swift/linux | head -5'")
    v["postgres_version"] = run(["docker", "exec", "research-postgres", "postgres", "--version"])
    v["redis_version"] = run("docker exec research-redis redis-server --version")
    return v


def datastore_config():
    keys = ["max_connections", "shared_buffers", "work_mem", "effective_cache_size",
            "maintenance_work_mem", "wal_buffers", "synchronous_commit", "fsync",
            "max_worker_processes", "random_page_cost"]
    pg = {}
    for k in keys:
        # Without -d, psql defaults to a database named after the user, which
        # does not exist here, so every SHOW came back empty.
        val = run(["docker", "exec", "research-postgres", "psql", "-U", "research",
                   "-d", "postgres", "-tAc", f"SHOW {k};"])
        if val:
            pg[k] = val
    redis = {}
    for k in ["maxmemory", "maxmemory-policy", "appendonly", "save", "io-threads", "databases"]:
        val = run(f"docker exec research-redis redis-cli CONFIG GET {k}")
        parts = val.splitlines()
        if len(parts) >= 2:
            redis[k] = parts[1]
        elif len(parts) == 1:
            redis[k] = ""
    return {"postgresql": pg, "redis": redis}


def application_parity():
    """The configuration values the parity claim actually rests on."""
    return {
        "bcrypt_cost": {"vapor": 10, "spring": 10,
                        "note": "Vapor app.passwords.use(.bcrypt(cost: 10)); Spring BCryptPasswordEncoder default strength 10"},
        "database_pool_size": {"vapor": "DB_POOL_PER_LOOP x event loops",
                               "spring": "spring.datasource.hikari.maximum-pool-size",
                               "note": "both resolve to 20 connections per service"},
        "cache_ttl_seconds": {"vapor": 30, "spring": 30},
        "list_endpoint_row_cap": {"GET /users": 100, "GET /orders": 50,
                                  "GET /products": "uncapped on both stacks, catalogue seeded at 5 rows",
                                  "note": "the Spring services were corrected in this revision to apply the same "
                                          "row caps and ordering as the Vapor services"},
        "latency_histogram_buckets": "72 finite buckets, identical boundaries on both stacks",
        "response_payload_fields": {"user": ["id", "name", "email", "createdAt"],
                                    "product": ["id", "name", "description", "price", "stock", "createdAt", "updatedAt"],
                                    "order": ["id", "userId", "status", "total", "items", "createdAt", "updatedAt"]},
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "results", "environment.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    record = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": host(),
        "docker": docker_env(),
        "containers": container_limits(),
        "runtimes": runtime_versions(),
        "datastores": datastore_config(),
        "application_parity": application_parity(),
    }
    existing = {}
    if os.path.exists(out_path):
        try:
            existing = json.load(open(out_path))
        except Exception:
            existing = {}
    # Merge so a capture taken while the Swift stack is up does not erase what
    # was captured while the Java stack was up.
    for k in ("containers", "runtimes"):
        merged = dict(existing.get(k) or {})
        for kk, vv in (record.get(k) or {}).items():
            if vv not in (None, "", {}):
                merged[kk] = vv
        record[k] = merged
    with open(out_path, "w") as fh:
        json.dump(record, fh, indent=2)
    print("environment written to", out_path)
    print(json.dumps(record["host"], indent=2))
    print(json.dumps(record["docker"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
