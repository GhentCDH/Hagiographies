// The Svelte build has to exist before the RustEmbed derive expands, so it runs
// here rather than being a separate step someone can forget. SKIP_FRONTEND_BUILD
// is the escape hatch used by the Dockerfile, which builds the frontend in its
// own stage and copies the result in.

fn main() {
    println!("cargo:rerun-if-changed=frontend/src");
    println!("cargo:rerun-if-changed=frontend/index.html");
    println!("cargo:rerun-if-changed=frontend/package.json");
    println!("cargo:rerun-if-changed=frontend/vite.config.ts");
    println!("cargo:rerun-if-env-changed=SKIP_FRONTEND_BUILD");

    if std::env::var_os("SKIP_FRONTEND_BUILD").is_some() {
        return;
    }

    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let frontend_dir = format!("{manifest_dir}/frontend");

    if !std::path::Path::new(&frontend_dir).exists() {
        println!("cargo:warning=frontend/ not found, skipping frontend build");
        return;
    }

    let status = std::process::Command::new("bun")
        .args(["run", "build"])
        .current_dir(&frontend_dir)
        .status()
        .expect("bun not found — install Bun (https://bun.sh) to build the frontend");

    if !status.success() {
        panic!("frontend build failed");
    }
}
