"""Apply one content-addressed, explicitly bounded source patch on a review branch."""
from __future__ import annotations
import gzip, hashlib, json, os, io, re
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRANCH = 'feat/desktop-delivery-20260925'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None

def main():
    if os.environ['GITHUB_REF'] != 'refs/heads/' + BRANCH:
        raise SystemExit('Ref outside authorized delivery branch')
    repo = os.environ['GITHUB_REPOSITORY']
    expected = os.environ['DESKTOP_PATCH_SHA256']
    parts = sorted((ROOT / '.desktop_upgrade').glob('part[0-9][0-9].bin'))
    if not parts or sum(p.stat().st_size for p in parts) > 150000:
        raise SystemExit('Missing/oversized source patch')
    with gzip.GzipFile(fileobj=io.BytesIO(b''.join(p.read_bytes() for p in parts))) as f:
        raw = f.read(300001)
    if len(raw) > 300000 or hashlib.sha256(raw).hexdigest() != expected:
        raise SystemExit('Source patch identity mismatch')
    payload = json.loads(raw)
    if payload['schema'] != 'bounded_desktop_patch_v1' or payload['repository'] != repo:
        raise SystemExit('Wrong patch repository/schema')
    files = payload['files']
    if not 1 <= len(files) <= 40:
        raise SystemExit('Unexpected patch scope')
    protected = {'.github', 'benchmarks', '.git', 'runs', 'data'}
    for rel, hashes in files.items():
        path = PurePosixPath(rel)
        if (path.is_absolute() or '..' in path.parts or '\\' in rel or ':' in rel or
                path.parts[0] in protected or path.suffix.lower() not in {'.py','.js','.html','.md','.json'}):
            raise SystemExit('Unauthorized path: ' + rel)
        dest = ROOT / rel
        if dest.is_symlink() or not dest.resolve().is_relative_to(ROOT.resolve()):
            raise SystemExit('Unsafe source path: ' + rel)
        for h in hashes.values():
            if h is not None and (len(h) != 64 or any(c not in '0123456789abcdef' for c in h)):
                raise SystemExit('Invalid expected digest')
    if all(digest(ROOT / p) == h['after'] for p,h in files.items()):
        commit = git('rev-parse','HEAD')
    else:
        for rel, hashes in files.items():
            if digest(ROOT / rel) != hashes['before']:
                raise SystemExit('Concurrent/changed source: ' + rel)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',delete=False,suffix='.patch') as f:
            text = payload['patch']
            text = re.sub(r'(?<=[^\n])(--- (?:a/[^\n]*|/dev/null)\n\+\+\+ b/)', lambda m: '\n\\ No newline at end of file\n' + m.group(1), text)
            if not text.endswith('\n'): text += '\n\\ No newline at end of file\n'
            f.write(text); patch = f.name
        try:
            subprocess.run(['git','apply','--check',patch],cwd=ROOT,check=True)
            subprocess.run(['git','apply',patch],cwd=ROOT,check=True)
        finally:
            Path(patch).unlink(missing_ok=True)
        for rel, hashes in files.items():
            if digest(ROOT / rel) != hashes['after']:
                raise SystemExit('Post-apply mismatch: ' + rel)
        subprocess.run(['git','add','--',*files],cwd=ROOT,check=True)
        changed = set(git('diff','--cached','--name-only').splitlines())
        if changed != set(files):
            raise SystemExit('Staged path set does not match bounded patch')
        remote = git('ls-remote','origin','refs/heads/'+BRANCH).split()[0]
        current = git('rev-parse','HEAD')
        if remote != current or current != os.environ['GITHUB_SHA']:
            raise SystemExit('Remote branch changed; reconciliation required')
        git('config','user.name','github-actions[bot]')
        git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        git('commit','-m','feat: expand verified desktop delivery source and regression tests')
        commit = git('rev-parse','HEAD')
        subprocess.run(['git','push','origin','HEAD:refs/heads/'+BRANCH],cwd=ROOT,check=True)
        if git('ls-remote','origin','refs/heads/'+BRANCH).split()[0] != commit:
            raise SystemExit('Remote publication readback mismatch')
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        f.write('source_commit='+commit+'\n')
    print(json.dumps({'repository':repo,'source_commit':commit,'bounded_files':len(files)}))

if __name__ == '__main__': main()
