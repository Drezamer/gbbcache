#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, sqlite3, sys, tempfile, time
from pathlib import Path
import unicodedata

COLS = [
    'id','name','yearpublished','rank','bayesaverage','average','usersrated','is_expansion',
    'abstracts_rank','cgs_rank','childrensgames_rank','familygames_rank','partygames_rank',
    'strategygames_rank','thematic_rank','wargames_rank'
]
INT_COLS = {'id','yearpublished','rank','usersrated','is_expansion','abstracts_rank','cgs_rank','childrensgames_rank','familygames_rank','partygames_rank','strategygames_rank','thematic_rank','wargames_rank'}
REAL_COLS = {'bayesaverage','average'}
SCHEMA = '''
CREATE TABLE games (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 name_norm TEXT NOT NULL,
 yearpublished INTEGER,
 rank INTEGER NOT NULL DEFAULT 0,
 bayesaverage REAL,
 average REAL,
 usersrated INTEGER NOT NULL DEFAULT 0,
 is_expansion INTEGER NOT NULL DEFAULT 0,
 abstracts_rank INTEGER,
 cgs_rank INTEGER,
 childrensgames_rank INTEGER,
 familygames_rank INTEGER,
 partygames_rank INTEGER,
 strategygames_rank INTEGER,
 thematic_rank INTEGER,
 wargames_rank INTEGER
);
'''
INDEXES = '''
CREATE INDEX idx_games_name_norm ON games(name_norm);
CREATE INDEX idx_games_rank ON games(rank);
CREATE INDEX idx_games_usersrated ON games(usersrated DESC);
CREATE INDEX idx_games_year ON games(yearpublished);
CREATE INDEX idx_games_expansion ON games(is_expansion);
CREATE INDEX idx_games_abstracts_rank ON games(abstracts_rank);
CREATE INDEX idx_games_cgs_rank ON games(cgs_rank);
CREATE INDEX idx_games_childrensgames_rank ON games(childrensgames_rank);
CREATE INDEX idx_games_familygames_rank ON games(familygames_rank);
CREATE INDEX idx_games_partygames_rank ON games(partygames_rank);
CREATE INDEX idx_games_strategygames_rank ON games(strategygames_rank);
CREATE INDEX idx_games_thematic_rank ON games(thematic_rank);
CREATE INDEX idx_games_wargames_rank ON games(wargames_rank);
'''

def norm(s):
    s = unicodedata.normalize('NFKC', s or '').casefold().strip()
    return ' '.join(s.split())

def parse_int(v):
    if v is None or v == '': return None
    return int(v)

def parse_real(v):
    if v is None or v == '': return None
    return float(v)

def canonical_row(r):
    return {
        'id': int(r['id']), 'name': r['name'].strip(), 'name_norm': norm(r['name']),
        'yearpublished': parse_int(r['yearpublished']), 'rank': int(r['rank'] or 0),
        'bayesaverage': parse_real(r['bayesaverage']), 'average': parse_real(r['average']),
        'usersrated': int(r['usersrated'] or 0), 'is_expansion': int(r['is_expansion'] or 0),
        'abstracts_rank': parse_int(r['abstracts_rank']), 'cgs_rank': parse_int(r['cgs_rank']),
        'childrensgames_rank': parse_int(r['childrensgames_rank']), 'familygames_rank': parse_int(r['familygames_rank']),
        'partygames_rank': parse_int(r['partygames_rank']), 'strategygames_rank': parse_int(r['strategygames_rank']),
        'thematic_rank': parse_int(r['thematic_rank']), 'wargames_rank': parse_int(r['wargames_rank'])
    }

def validate_row(g, suspicious):
    if g['id'] <= 0: raise ValueError(f"invalid id {g['id']}")
    if not g['name']: raise ValueError(f"empty name id {g['id']}")
    if g['rank'] < 0: raise ValueError(f"negative rank id {g['id']}")
    y = g['yearpublished']
    if y is not None and (y < -10000 or y > 2100):
        # Flag only; never modify. Historical years and near-future releases remain valid data.
        suspicious.append({'id':g['id'],'name':g['name'],'field':'yearpublished','value':y,'reason':'outside plausible review window'})
    if g['rank'] > 0 and g['rank'] > 1000000: suspicious.append({'id':g['id'],'name':g['name'],'field':'rank','value':g['rank'],'reason':'unusually large'})

def logical_hash(con):
    h = hashlib.sha256()
    sql = """SELECT CAST(id AS TEXT), name, name_norm,
        CASE WHEN yearpublished IS NULL THEN '' ELSE CAST(yearpublished AS TEXT) END,
        CAST(rank AS TEXT),
        CASE WHEN bayesaverage IS NULL THEN '' ELSE printf('%.17g', bayesaverage) END,
        CASE WHEN average IS NULL THEN '' ELSE printf('%.17g', average) END,
        CAST(usersrated AS TEXT), CAST(is_expansion AS TEXT),
        CASE WHEN abstracts_rank IS NULL THEN '' ELSE CAST(abstracts_rank AS TEXT) END,
        CASE WHEN cgs_rank IS NULL THEN '' ELSE CAST(cgs_rank AS TEXT) END,
        CASE WHEN childrensgames_rank IS NULL THEN '' ELSE CAST(childrensgames_rank AS TEXT) END,
        CASE WHEN familygames_rank IS NULL THEN '' ELSE CAST(familygames_rank AS TEXT) END,
        CASE WHEN partygames_rank IS NULL THEN '' ELSE CAST(partygames_rank AS TEXT) END,
        CASE WHEN strategygames_rank IS NULL THEN '' ELSE CAST(strategygames_rank AS TEXT) END,
        CASE WHEN thematic_rank IS NULL THEN '' ELSE CAST(thematic_rank AS TEXT) END,
        CASE WHEN wargames_rank IS NULL THEN '' ELSE CAST(wargames_rank AS TEXT) END
        FROM games ORDER BY id"""
    for row in con.execute(sql):
        h.update(('\x1f'.join(str(x) for x in row) + '\x1e').encode('utf-8'))
    return h.hexdigest()

def build(csv_path, out_path):
    csv_path, out_path = Path(csv_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=out_path.name+'.', suffix='.tmp', dir=str(out_path.parent)); os.close(fd)
    try:
        con = sqlite3.connect(tmp)
        con.executescript(SCHEMA)
        ins = '''INSERT INTO games (id,name,name_norm,yearpublished,rank,bayesaverage,average,usersrated,is_expansion,abstracts_rank,cgs_rank,childrensgames_rank,familygames_rank,partygames_rank,strategygames_rank,thematic_rank,wargames_rank) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
        seen=set(); suspicious=[]; count=0
        with csv_path.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames is None or any(c not in reader.fieldnames for c in COLS):
                raise RuntimeError(f'CSV columns missing; got {reader.fieldnames}')
            for raw in reader:
                g=canonical_row(raw)
                if g['id'] in seen: raise ValueError(f'duplicate id {g["id"]}')
                seen.add(g['id']); validate_row(g,suspicious)
                con.execute(ins, tuple(g[c] for c in ['id','name','name_norm','yearpublished','rank','bayesaverage','average','usersrated','is_expansion','abstracts_rank','cgs_rank','childrensgames_rank','familygames_rank','partygames_rank','strategygames_rank','thematic_rank','wargames_rank']))
                count += 1
        con.executescript(INDEXES)
        con.execute('ANALYZE')
        con.commit()
        con.close()
        os.replace(tmp,out_path)
        sha=hashlib.sha256(out_path.read_bytes()).hexdigest()
        con=sqlite3.connect(out_path)
        info={
            'schema_version':1,'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'sha256':sha,'logical_sha256':logical_hash(con),'games':con.execute('SELECT COUNT(*) FROM games').fetchone()[0],
            'ranked':con.execute('SELECT COUNT(*) FROM games WHERE rank>0').fetchone()[0],
            'expansions':con.execute('SELECT COUNT(*) FROM games WHERE is_expansion=1').fetchone()[0],
            'suspicious_count':len(suspicious),'suspicious':suspicious[:500]
        }
        con.close()
        manifest=out_path.with_suffix('.manifest.json'); manifest.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(info,ensure_ascii=False,indent=2))
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('output'); args=ap.parse_args(); build(args.csv,args.output)
