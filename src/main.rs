use std::{env, io, path::PathBuf, process};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args_os().skip(1);
    let command = args.next().ok_or("Usage: schoolhub-scan scan PATH [WORKERS]")?;
    if command != "scan" { return Err("Unknown command".into()); }
    let root = PathBuf::from(args.next().ok_or("Missing root")?);
    let workers = match args.next() {
        Some(n) => n.to_str().ok_or("Invalid worker count")?.parse::<usize>()?,
        None => std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).min(4),
    };
    if args.next().is_some() || !(1..=8).contains(&workers) {
        return Err("Expected 1–8 workers".into());
    }
    let files = schoolhub_scan::scan(&root, workers)?;
    serde_json::to_writer(io::stdout().lock(), &files)?;
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        process::exit(1);
    }
}
