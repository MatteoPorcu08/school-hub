use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File, Metadata},
    io::{self, Read},
    path::{Path, PathBuf},
};
use walkdir::WalkDir;

pub type FileMap = BTreeMap<String, String>;

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn is_reparse(meta: &Metadata) -> bool {
    if meta.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        // Reject Windows junctions and other reparse points, not just symlinks.
        if meta.file_attributes() & 0x400 != 0 {
            return true;
        }
    }
    false
}

fn hash_file(path: &Path) -> io::Result<String> {
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() || is_reparse(&before) {
        return Err(invalid(format!("File non regolare: {}", path.display())));
    }
    let mut file = File::open(path)?;
    let opened = file.metadata()?;
    if !opened.is_file() || opened.len() != before.len()
        || opened.modified()? != before.modified()? {
        return Err(invalid(format!("File modificato durante l'apertura: {}", path.display())));
    }
    let mut sha = Sha256::new();
    let mut buffer = vec![0_u8; 256 * 1024];
    let mut read_total = 0_u64;
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 { break; }
        sha.update(&buffer[..n]);
        read_total += n as u64;
    }
    let after = fs::symlink_metadata(path)?;
    let handle_after = file.metadata()?;
    if is_reparse(&after) || !after.is_file()
        || read_total != before.len()
        || before.len() != after.len()
        || before.modified()? != after.modified()?
        || handle_after.len() != before.len()
        || handle_after.modified()? != before.modified()? {
        return Err(invalid(format!("File modificato durante la scansione: {}", path.display())));
    }
    Ok(format!("{:x}", sha.finalize()))
}

fn relative_name(root: &Path, path: &Path) -> io::Result<String> {
    let rel = path.strip_prefix(root).map_err(|e| invalid(e.to_string()))?;
    rel.components().map(|component| {
        component.as_os_str().to_str().map(str::to_owned)
            .ok_or_else(|| invalid("Percorso non UTF-8"))
    }).collect::<io::Result<Vec<_>>>().map(|parts| parts.join("/"))
}

/// Scan real file contents every time. Do not rely on size/mtime to skip hashing.
/// Never include Git internals or the repository's root .gitattributes.
pub fn scan(root: &Path, workers: usize) -> io::Result<FileMap> {
    let meta = fs::symlink_metadata(root)?;
    if !meta.is_dir() || is_reparse(&meta) {
        return Err(invalid("La radice deve essere una cartella reale"));
    }
    let mut entries: Vec<(String, PathBuf)> = Vec::new();
    let walker = WalkDir::new(root).follow_links(false).into_iter()
        .filter_entry(|e| e.depth() == 0 || !(e.file_type().is_dir() && e.file_name() == ".git"));
    for entry in walker {
        let entry = entry.map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;
        if entry.depth() == 0 { continue; }
        let path = entry.path();
        let meta = fs::symlink_metadata(path)?;
        if is_reparse(&meta) {
            return Err(invalid(format!("Collegamento non supportato: {}", path.display())));
        }
        if meta.is_dir() { continue; }
        if !meta.is_file() {
            return Err(invalid(format!("File non regolare: {}", path.display())));
        }
        let rel = relative_name(root, path)?;
        if rel == ".gitattributes" { continue; }
        // On Unix a literal backslash is ambiguous in SchoolHub's path model.
        if rel.contains('\\') {
            return Err(invalid(format!("Percorso ambiguo: {rel}")));
        }
        entries.push((rel, path.to_owned()));
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(workers.clamp(1, 8))
        .build().map_err(|e| invalid(e.to_string()))?;
    let pairs: io::Result<Vec<_>> = pool.install(|| entries.par_iter().map(|(name, path)| {
        hash_file(path).map(|hash| (name.clone(), hash))
            .map_err(|e| io::Error::new(e.kind(), format!("{}: {e}", path.display())))
    }).collect());
    Ok(pairs?.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hashes_recursive_tree_and_excludes_git() {
        let root = tempfile::tempdir().unwrap();
        fs::create_dir_all(root.path().join("docs/.git")).unwrap();
        fs::write(root.path().join("docs/.git/config"), b"secret").unwrap();
        fs::write(root.path().join(".gitattributes"), b"ignored").unwrap();
        fs::write(root.path().join("docs/hello.txt"), b"abc").unwrap();
        fs::write(root.path().join("docs/.gitattributes"), b"nested").unwrap();
        let result = scan(root.path(), 2).unwrap();
        assert_eq!(result.len(), 2);
        assert_eq!(result["docs/hello.txt"], "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        assert!(result.contains_key("docs/.gitattributes"));
        assert_eq!(result, scan(root.path(), 1).unwrap());
    }
    #[test]
    fn detects_same_size_content_change_and_deletion() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("test");
        fs::write(&path, b"one").unwrap();
        let a = scan(root.path(), 1).unwrap();
        fs::write(&path, b"two").unwrap();
        let b = scan(root.path(), 2).unwrap();
        assert_ne!(a, b);
        fs::remove_file(path).unwrap();
        assert!(scan(root.path(), 2).unwrap().is_empty());
    }
    #[cfg(unix)]
    #[test]
    fn rejects_symlinks() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join("real"), b"x").unwrap();
        std::os::unix::fs::symlink(root.path().join("real"), root.path().join("link")).unwrap();
        assert!(scan(root.path(), 2).is_err());
    }
}
