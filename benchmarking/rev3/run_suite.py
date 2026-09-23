#!/usr/bin/env python3
"""
Sequential benchmark driver for revision 3.

One stack, one configuration and one scenario per run. Runs never overlap, so
the system under test owns its CPU quota for the whole measured window and the
only other load on the host is the sampler and k6, both of which are measured.

Repetitions are interleaved rather than blocked: the driver completes
repetition 1 of every (configuration, scenario) pair before starting
repetition 2. If the suite is interrupted, what survives is a balanced design
rather than complete data for the configurations that happened to run first.
Configuration order is rotated each repetition so that any drift in the host over
the night, thermal or otherwise, does not land on the same configuration twice.

Completed runs are skipped on restart, so the suite is resumable.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INFRA = os.path.join(ROOT, "infrastructure")
REV3 = os.path.join(ROOT, "benchmarking", "rev3")
COMPOSE = ["docker", "compose",
           "-f", os.path.join(INFRA, "docker-compose.yml"),
           "-f", os.path.join(INFRA, "docker-compose.parity.yml")]

SWIFT_SVCS = ["swift-user-service", "swift-product-service", "swift-order-service"]
JAVA_SVCS = ["java-user-service", "java-product-service", "java-order-service"]

# The four configurations under comparison. The Java side is deliberately not
# left at its defaults: a default Tomcat pool, a pool matched to the Vapor
# blocking-pool size, and virtual threads bracket the Java configuration space,
# so the result is not an artefact of one arbitrary setting.
CONFIGS = {
    "vapor": {
        "target": "swift",
        "services": SWIFT_SVCS,
        "env": {"EVENT_LOOPS": "2", "BLOCKING_THREADS": "64", "DB_POOL_PER_LOOP": "10",
                "SWIFT_ENV": "production"},
        "label": "Vapor (2 event loops, 64 blocking threads)",
    },
    "boot-t200": {
        "target": "java",
        "services": JAVA_SVCS,
        "env": {"TOMCAT_THREADS_MAX": "200", "VIRTUAL_THREADS": "false"},
        "label": "Spring Boot, Tomcat platform threads, max 200 (framework default)",
    },
    "boot-t64": {
        "target": "java",
        "services": JAVA_SVCS,
        "env": {"TOMCAT_THREADS_MAX": "64", "VIRTUAL_THREADS": "false"},
        "label": "Spring Boot, Tomcat platform threads, max 64 (matched to Vapor blocking pool)",
    },
    "boot-vt": {
        "target": "java",
        "services": JAVA_SVCS,
        "env": {"TOMCAT_THREADS_MAX": "200", "VIRTUAL_THREADS": "true"},
        "label": "Spring Boot, virtual threads (Java 21, spring.threads.virtual.enabled)",
    },
}

SCENARIOS = ["load", "stress", "spike", "soak"]

HEALTH = {
    "swift": ["http://localhost:8081/health", "http://localhost:8082/health", "http://localhost:8083/health"],
    "java": ["http://localhost:9081/actuator/health", "http://localhost:9082/actuator/health",
             "http://localhost:9083/actuator/health"],
}

DBS = {
    "swift": [("swift_user_db", ["users"]),
              ("swift_product_db", ["products"]),
              ("swift_order_db", ["order_items", "orders"])],
    "java": [("java_user_db", ["users"]),
             ("java_product_db", ["products"]),
             ("java_order_db", ["order_items", "orders"])],
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd, env=None, timeout=900, check=True):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run(cmd, env=e, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        log(f"command failed ({p.returncode}): {' '.join(cmd[:6])}...")
        log(p.stderr[-1500:])
    return p


def reset_state(target):
    """Empty the tables and the cache so every run starts from the same size.

    Without this the list endpoints answer from a table that grows with every
    write of every previous run, and latency drifts upward across repetitions
    for reasons that have nothing to do with the framework.
    """
    for db, tables in DBS[target]:
        stmt = "TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE;"
        sh(["docker", "exec", "research-postgres", "psql", "-U", "research", "-d", db, "-c", stmt],
           timeout=60, check=False)
    sh(["docker", "exec", "research-redis", "redis-cli", "FLUSHALL"], timeout=60, check=False)


def wait_healthy(target, timeout=240):
    deadline = time.time() + timeout
    remaining = list(HEALTH[target])
    while time.time() < deadline:
        still = []
        for url in remaining:
            try:
                with urllib.request.urlopen(url, timeout=4) as r:
                    if r.status != 200:
                        still.append(url)
            except Exception:
                still.append(url)
        remaining = still
        if not remaining:
            return True
        time.sleep(3)
    log(f"TIMED OUT waiting for: {remaining}")
    return False


def bring_up_infra():
    log("starting postgres and redis")
    sh(COMPOSE + ["up", "-d", "postgres", "redis"], timeout=300)
    for _ in range(40):
        p = sh(["docker", "exec", "research-postgres", "pg_isready", "-U", "research"],
               timeout=30, check=False)
        if p.returncode == 0:
            return True
        time.sleep(3)
    return False


def run_one(cfg_name, scenario, rep, outdir, warmup):
    cfg = CONFIGS[cfg_name]
    run_id = f"{cfg_name}_{scenario}_rep{rep}"
    summary_path = os.path.join(outdir, f"{run_id}_k6summary.json")
    if os.path.exists(summary_path):
        log(f"skip {run_id} (already complete)")
        return True

    log(f"=== {run_id} : {cfg['label']} ===")
    env = dict(cfg["env"])

    # Recreate the containers so the configuration change takes effect and the
    # process starts with a clean heap. Memory numbers are only comparable if
    # every run begins from the same cold state.
    sh(COMPOSE + ["rm", "-sf"] + cfg["services"], env=env, timeout=300, check=False)
    reset_state(cfg["target"])
    p = sh(COMPOSE + ["up", "-d", "--force-recreate"] + cfg["services"], env=env, timeout=600)
    if p.returncode != 0:
        log(f"FAILED to start {run_id}")
        return False

    if not wait_healthy(cfg["target"]):
        log(f"FAILED health check for {run_id}")
        sh(COMPOSE + ["stop"] + cfg["services"], env=env, timeout=300, check=False)
        return False
    time.sleep(10)  # settle after the health endpoint first answers

    # Send the sampler's diagnostics to a file. Holding them in a pipe nobody
    # reads will block the sampler once the buffer fills, and then the reason
    # for a missing snapshot is lost along with the snapshot.
    sampler_log = open(os.path.join(outdir, f"{run_id}_sampler.log"), "w")
    # Warm up in a separate process, before the sampler opens the measured
    # window. Just in time compilation and lazy initialisation are paid for
    # here, and none of these requests reach either measurement point.
    warm_env = {"TARGET": cfg["target"], "WARMUP_REQUESTS": str(warmup)}
    if cfg["target"] == "swift":
        warm_env.update({"USER_URL": "http://localhost:8081",
                         "PRODUCT_URL": "http://localhost:8082"})
    else:
        warm_env.update({"USER_URL": "http://localhost:9081",
                         "PRODUCT_URL": "http://localhost:9082"})
    wp = sh(["k6", "run", "--quiet", os.path.join(REV3, "scenarios", "warmup.js")],
            env=warm_env, timeout=900, check=False)
    if wp.returncode != 0:
        log(f"warm-up returned {wp.returncode} for {run_id}")
    time.sleep(3)

    sampler = subprocess.Popen(
        [sys.executable, os.path.join(REV3, "sampler.py"),
         "--target", cfg["target"], "--outdir", outdir, "--run-id", run_id],
        stdout=sampler_log, stderr=subprocess.STDOUT)
    time.sleep(2)

    k6_env = {
        "TARGET": cfg["target"],
        "SCENARIO": scenario,
        "SUMMARY_PATH": summary_path + ".tmp",
    }
    if cfg["target"] == "swift":
        k6_env.update({"USER_URL": "http://localhost:8081",
                       "PRODUCT_URL": "http://localhost:8082",
                       "ORDER_URL": "http://localhost:8083"})
    else:
        k6_env.update({"USER_URL": "http://localhost:9081",
                       "PRODUCT_URL": "http://localhost:9082",
                       "ORDER_URL": "http://localhost:9083"})

    t0 = time.time()
    kp = sh(["k6", "run", "--quiet",
             os.path.join(REV3, "scenarios", "bench.js")],
            env=k6_env, timeout=2400, check=False)
    elapsed = time.time() - t0

    with open(os.path.join(outdir, f"{run_id}_k6.log"), "w") as fh:
        fh.write(kp.stdout or "")
        fh.write("\n--- stderr ---\n")
        fh.write(kp.stderr or "")

    sampler.send_signal(signal.SIGINT)
    try:
        sampler.wait(timeout=180)
    except subprocess.TimeoutExpired:
        log(f"sampler did not exit in time for {run_id}, terminating")
        sampler.kill()
        sampler.wait(timeout=30)
    sampler_log.close()

    hist_path = os.path.join(outdir, f"{run_id}_histograms.json")
    if not os.path.exists(hist_path):
        log(f"WARNING no server-side histogram snapshot for {run_id}; "
            f"see {run_id}_sampler.log")

    ok = os.path.exists(summary_path + ".tmp")
    if ok:
        os.replace(summary_path + ".tmp", summary_path)
    else:
        log(f"k6 produced no summary for {run_id} (rc={kp.returncode})")

    with open(os.path.join(outdir, f"{run_id}_meta.json"), "w") as fh:
        json.dump({
            "run_id": run_id, "config": cfg_name, "config_label": cfg["label"],
            "target": cfg["target"], "scenario": scenario, "repetition": rep,
            "config_env": env, "k6_env": k6_env,
            "k6_returncode": kp.returncode, "k6_wall_seconds": elapsed,
            "finished_unix": time.time(),
            "finished_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, fh, indent=2)

    sh(COMPOSE + ["stop"] + cfg["services"], env=env, timeout=300, check=False)
    log(f"--- {run_id} done in {elapsed:.0f}s (k6 rc={kp.returncode})")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--outdir", default=os.path.join(REV3, "results"))
    ap.add_argument("--warmup", type=int, default=1500)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--start-rep", type=int, default=1)
    args = ap.parse_args()

    configs = [c for c in args.configs.split(",") if c in CONFIGS]
    scenarios = [s for s in args.scenarios.split(",") if s in SCENARIOS]
    os.makedirs(args.outdir, exist_ok=True)

    if not bring_up_infra():
        log("postgres never became ready, aborting")
        return 1

    total = args.reps * len(configs) * len(scenarios)
    done = 0
    t_suite = time.time()
    for rep in range(args.start_rep, args.start_rep + args.reps):
        order = configs[(rep - 1) % len(configs):] + configs[:(rep - 1) % len(configs)]
        for cfg_name in order:
            for scenario in scenarios:
                run_one(cfg_name, scenario, rep, args.outdir, args.warmup)
                done += 1
                el = time.time() - t_suite
                log(f"progress {done}/{total}  elapsed {el/60:.1f}m  eta {(el/max(done,1))*(total-done)/60:.1f}m")
    log("suite complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
