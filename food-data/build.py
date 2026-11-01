"""Publish only an attributed, text-only UK subset of the public OFF export."""
import csv, gzip, hashlib, io, json, math, os, re, sys, urllib.request
from pathlib import Path
from datetime import datetime, timezone

SOURCE='https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz'
OUT=Path('food-output')
def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) and n>=0 else None
    except (ValueError,TypeError): return None

def build(stream):
    csv.field_size_limit(sys.maxsize)
    rows=csv.DictReader(stream,delimiter='\t')
    assert {'code','countries_tags','ingredients_text','product_name'}.issubset(rows.fieldnames or []), 'Unrecognised export'
    buckets={str(i).zfill(2):{} for i in range(100)}
    for row in rows:
        if 'en:united-kingdom' not in (row.get('countries_tags') or '').split(','): continue
        code=(row.get('code') or '').strip()
        if not re.fullmatch(r'(?:\d{8}|\d{12,13})',code) or not (row.get('product_name') or '').strip(): continue
        p={k:row[k][:30000 if k=='ingredients_text' else 1000] for k in ['product_name','brands','quantity','ingredients_text','categories','stores','serving_size','nutriscore_grade'] if row.get(k)}
        p['nutrition_data_per']='100g'
        p['nutriments']={k:n for k in ['energy-kcal_100g','energy-kj_100g','proteins_100g','carbohydrates_100g','fat_100g','sugars_100g','saturated-fat_100g','salt_100g','sodium_100g','fiber_100g'] if (n:=number(row.get(k))) is not None}
        for dest,src in [('allergens_tags','allergens'),('traces_tags','traces_tags'),('additives_tags','additives_tags'),('labels_tags','labels_tags'),('countries_tags','countries_tags')]:
            p[dest]=[x.strip() for x in (row.get(src) or '').split(',') if x.strip()][:300]
        if (n:=number(row.get('last_modified_t'))) is not None: p['last_modified_t']=int(n)
        if (n:=number(row.get('nova_group'))) in (1,2,3,4): p['nova_group']=n
        if row.get('image_url','').startswith('https://images.openfoodfacts.org/'): p['image_url']=row['image_url']
        old=buckets[code[-2:]].get(code)
        if old is None or p.get('last_modified_t',0)>old.get('last_modified_t',0): buckets[code[-2:]][code]=p
    count=sum(map(len,buckets.values()))
    assert 10000<count<=500000, f'Unexpected UK record count: {count}; keep previous release'
    OUT.mkdir(exist_ok=True)
    files=[]
    def write(name,value):
        data=gzip.compress(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),compresslevel=9,mtime=0)
        assert len(data)<=12*1024**2, 'Shard too large for phones'
        (OUT/name).write_bytes(data)
        files.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    index=[]
    for suffix,products in buckets.items():
        write('products-'+suffix+'.json.bin',dict(sorted(products.items())))
        index.extend([code,p['product_name'],p.get('brands',''),p.get('quantity',''),p.get('stores','')] for code,p in sorted(products.items()))
    write('index.json.bin',index)
    revision=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    tag='food-'+revision[:16]
    for f in files: f['url']='https://github.com/Aidreaming/DAVE-APK/releases/download/'+tag+'/'+f['name']
    catalog={'format':'dave-food-catalog-v1','revision':revision,'publishedAt':datetime.now(timezone.utc).isoformat(),'products':count,'totalBytes':sum(f['bytes'] for f in files),'source':{'name':'Open Food Facts contributors','url':SOURCE,'licence':'ODbL 1.0; individual contents DbCL 1.0'},'files':files}
    assert catalog['totalBytes']<=100*1024**2
    (OUT/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    (OUT/'ATTRIBUTION.txt').write_text('Open Food Facts contributors — https://world.openfoodfacts.org\nDatabase: https://opendatacommons.org/licenses/odbl/1-0/\nContents: https://opendatacommons.org/licenses/dbcl/1-0/\nUK text subset, no photographs. Public extraction code: https://github.com/Aidreaming/DAVE-APK/blob/main/food-data/build.py\nSource export: '+SOURCE+'\n')
    print(tag)
    with open(os.environ.get('GITHUB_OUTPUT','/tmp/dave-food-output'),'a') as output: output.write('tag='+tag+'\n')

if __name__=='__main__':
    request=urllib.request.Request(SOURCE,headers={'User-Agent':'DAVE-Food database publisher (https://github.com/Aidreaming/DAVE-APK)'})
    with urllib.request.urlopen(request,timeout=120) as response, gzip.GzipFile(fileobj=response) as zipped:
        build(io.TextIOWrapper(zipped,encoding='utf-8'))
