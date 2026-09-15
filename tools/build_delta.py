#!/usr/bin/env python3
import argparse, gzip, hashlib, json, sqlite3, time
from pathlib import Path

FIELDS = [
    'id','name','name_norm','yearpublished','rank','bayesaverage','average','usersrated','is_expansion',
    'abstracts_rank','cgs_rank','childrensgames_rank','familygames_rank','partygames_rank','strategygames_rank',
    'thematic_rank','wargames_rank'
]
SOURCE_FIELDS = [f for f in FIELDS if f != 'name_norm']

HASH_QUERY = '''
SELECT
  CAST(id AS TEXT),
  name,
  name_norm,
  CASE WHEN yearpublished IS NULL THEN '' ELSE CAST(yearpublished AS TEXT) END,
  CAST(rank AS TEXT),
  CASE WHEN bayesaverage IS NULL THEN '' ELSE printf('%.17g', bayesaverage) END,
  CASE WHEN average IS NULL THEN '' ELSE printf('%.17g', average) END,
  CAST(usersrated AS TEXT),
  CAST(is_expansion AS TEXT),
  CASE WHEN abstracts_rank IS NULL THEN '' ELSE CAST(abstracts_rank AS TEXT) END,
  CASE WHEN cgs_rank IS NULL THEN '' ELSE CAST(cgs_rank AS TEXT) END,
  CASE WHEN childrensgames_rank IS NULL THEN '' ELSE CAST(childrensgames_rank AS TEXT) END,
  CASE WHEN familygames_rank IS NULL THEN '' ELSE CAST(familygames_rank AS TEXT) END,
  CASE WHEN partygames_rank IS NULL THEN '' ELSE CAST(partygames_rank AS TEXT) END,
  CASE WHEN strategygames_rank IS NULL THEN '' ELSE CAST(strategygames_rank AS TEXT) END,
  CASE WHEN thematic_rank IS NULL THEN '' ELSE CAST(thematic_rank AS TEXT) END,
  CASE WHEN wargames_rank IS NULL THEN '' ELSE CAST(wargames_rank AS TEXT) END
FROM games
ORDER BY id
'''


def logical_hash(con):
    h = hashlib.sha256()
    cur = con.execute(HASH_QUERY)
    for row in cur:
        h.update(('\x1f'.join(str(x) for x in row) + '\x1e').encode('utf-8'))
    return h.hexdigest()


def rowdict(r):
    return {k: r[k] for k in FIELDS}


def rowhash(r):
    return hashlib.sha256(
        json.dumps(
            {k: r[k] for k in SOURCE_FIELDS},
            ensure_ascii=False,
            separators=(',', ':'),
            sort_keys=True
        ).encode('utf-8')
    ).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old_db')
    ap.add_argument('new_db')
    ap.add_argument('delta_gz')
    args = ap.parse_args()

    old = sqlite3.connect(args.old_db)
    new = sqlite3.connect(args.new_db)
    old.row_factory = sqlite3.Row
    new.row_factory = sqlite3.Row

    old_cur = old.execute('SELECT * FROM games ORDER BY id')
    new_cur = new.execute('SELECT * FROM games ORDER BY id')
    old_row = old_cur.fetchone()
    new_row = new_cur.fetchone()
    counts = {'added': 0, 'changed': 0, 'removed': 0, 'unchanged': 0}

    delta_path = Path(args.delta_gz)
    with gzip.open(delta_path, 'wt', encoding='utf-8') as out:
        while old_row is not None or new_row is not None:
            oid = old_row['id'] if old_row is not None else None
            nid = new_row['id'] if new_row is not None else None

            if old_row is None or (new_row is not None and nid < oid):
                out.write(json.dumps(
                    {'op': 'upsert', 'row': rowdict(new_row)},
                    ensure_ascii=False,
                    separators=(',', ':')
                ) + '\n')
                counts['added'] += 1
                new_row = new_cur.fetchone()

            elif new_row is None or oid < nid:
                out.write(json.dumps(
                    {'op': 'delete', 'id': int(old_row['id'])},
                    separators=(',', ':')
                ) + '\n')
                counts['removed'] += 1
                old_row = old_cur.fetchone()

            else:
                if rowhash(old_row) != rowhash(new_row):
                    out.write(json.dumps(
                        {'op': 'upsert', 'row': rowdict(new_row)},
                        ensure_ascii=False,
                        separators=(',', ':')
                    ) + '\n')
                    counts['changed'] += 1
                else:
                    counts['unchanged'] += 1
                old_row = old_cur.fetchone()
                new_row = new_cur.fetchone()

    old_logical_sha256 = logical_hash(old)
    new_logical_sha256 = logical_hash(new)
    old_physical_sha256 = hashlib.sha256(Path(args.old_db).read_bytes()).hexdigest()
    new_physical_sha256 = hashlib.sha256(Path(args.new_db).read_bytes()).hexdigest()
    delta_sha256 = hashlib.sha256(delta_path.read_bytes()).hexdigest()

    old_games = old.execute('SELECT COUNT(*) FROM games').fetchone()[0]
    old_ranked = old.execute('SELECT COUNT(*) FROM games WHERE rank > 0').fetchone()[0]
    new_games = new.execute('SELECT COUNT(*) FROM games').fetchone()[0]
    new_ranked = new.execute('SELECT COUNT(*) FROM games WHERE rank > 0').fetchone()[0]

    old.close()
    new.close()

    manifest = delta_path.with_suffix('.manifest.json')
    m = {
        'schema_version': 2,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'old_sha256': old_physical_sha256,
        'new_sha256': new_physical_sha256,
        'old_logical_sha256': old_logical_sha256,
        'new_logical_sha256': new_logical_sha256,
        'delta_sha256': delta_sha256,
        'old_games': int(old_games),
        'old_ranked': int(old_ranked),
        'new_games': int(new_games),
        'new_ranked': int(new_ranked),
        'counts': counts,
        'delta_bytes': delta_path.stat().st_size
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(m, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
