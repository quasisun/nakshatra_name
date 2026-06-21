#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка офлайн-базы городов для «Накшатра Луны».
Вход: GeoNames RU.txt + altnames/RU.txt + cities5000.txt + admin1CodesASCII.txt + countryInfo.txt
Выход: data/cities.txt(.gz) (name\tlatE4\tlonE4\tadminIdx\tzoneIdx) + data/cities-meta.json {zones, admins}
Луна геоцентрична → координаты нужны только для часового пояса, точности 4 знака хватает с запасом.
Имена регионов/районов берём из русских альт-имён GeoNames, ПРЕДПОЧИТАЯ официальную форму
(содержащую «область/край/республика/округ/район»), чтобы не попадались падежи и разговорные варианты.
"""
import os, json, gzip, io, re

SP = "/private/tmp/claude-501/-Users-svetlanakreuzer/b73d17dc-3143-4ed7-a145-cb4f4be76d82/scratchpad/geonames"
OUT = "/Users/svetlanakreuzer/jyotish-nakshatra/data"
os.makedirs(OUT, exist_ok=True)
CYR = re.compile('[А-Яа-яЁё]')

# ---- Транслитерация латиница→кириллица для деревень без русского имени в GeoNames ----
_TR = {
 'shch':'щ','sch':'щ','zh':'ж','kh':'х','ts':'ц','ch':'ч','sh':'ш',
 'yo':'ё','yu':'ю','ya':'я','ye':'е','yi':'йи',
 'ay':'ай','oy':'ой','ey':'ей','uy':'уй','yy':'ый','iy':'ий',
 'a':'а','b':'б','v':'в','g':'г','d':'д','e':'е','z':'з','i':'и','y':'ы',
 'k':'к','l':'л','m':'м','n':'н','o':'о','p':'п','r':'р','s':'с','t':'т',
 'u':'у','f':'ф','h':'х','c':'ц','j':'ж','w':'в','x':'кс','q':'к',
 "'":'ь','’':'ь','`':'ь','"':'ъ',
}
_TR_KEYS = sorted(_TR.keys(), key=len, reverse=True)
def _tr_word(w):
    s = w.lower(); out = []; i = 0; n = len(s)
    while i < n:
        for k in _TR_KEYS:
            if s.startswith(k, i):
                out.append(_TR[k]); i += len(k); break
        else:
            out.append(s[i]); i += 1
    r = ''.join(out)
    return r[:1].upper() + r[1:] if r else r
def translit(name):
    return re.sub(r"[A-Za-z'’`\"]+", lambda m: _tr_word(m.group(0)), name)

_LOWER = {'Область','Край','Район','Округ','Автономный','Автономная','Городской','Городского',
          'Поселение','Сельское','Сельсовет','Республика'}
def fix_case(s):
    s = s.replace('́', '')                       # убрать комбинирующее ударение (Кузба́сс)
    parts = s.split(' ')
    return ' '.join(w.lower() if i > 0 and w in _LOWER else w for i, w in enumerate(parts))

# Разговорные/обрезанные/неоднозначные субъекты → официальные (применяется после fix_case)
REGION_FIX = {
    'Орловщина': 'Орловская область', 'Ставрополье': 'Ставропольский край',
    'Сахалин': 'Сахалинская область', 'Тюмень': 'Тюменская область',
    'Челябинская': 'Челябинская область', 'Кузбасс': 'Кемеровская область',
    'Алтай': 'Республика Алтай',
}
OFFICIAL = re.compile('област|кра[ыйя]|республик|автономн|округ|район', re.I)

def first_cyr(s):
    for tok in s.split(','):
        tok = tok.strip()
        if tok and CYR.search(tok):
            return tok
    return None

COUNTRY_RU = {
 'RU':'Россия','UA':'Украина','BY':'Беларусь','KZ':'Казахстан','UZ':'Узбекистан',
 'KG':'Киргизия','TJ':'Таджикистан','TM':'Туркмения','AZ':'Азербайджан','AM':'Армения',
 'GE':'Грузия','MD':'Молдавия','LT':'Литва','LV':'Латвия','EE':'Эстония',
 'DE':'Германия','FR':'Франция','GB':'Великобритания','IT':'Италия','ES':'Испания',
 'PT':'Португалия','NL':'Нидерланды','BE':'Бельгия','CH':'Швейцария','AT':'Австрия',
 'PL':'Польша','CZ':'Чехия','SK':'Словакия','HU':'Венгрия','RO':'Румыния','BG':'Болгария',
 'GR':'Греция','RS':'Сербия','HR':'Хорватия','SI':'Словения','BA':'Босния и Герцеговина',
 'ME':'Черногория','MK':'Северная Македония','AL':'Албания','XK':'Косово',
 'SE':'Швеция','NO':'Норвегия','FI':'Финляндия','DK':'Дания','IS':'Исландия','IE':'Ирландия',
 'US':'США','CA':'Канада','MX':'Мексика','BR':'Бразилия','AR':'Аргентина','CL':'Чили',
 'CO':'Колумбия','PE':'Перу','VE':'Венесуэла','EC':'Эквадор','BO':'Боливия','UY':'Уругвай','PY':'Парагвай',
 'CN':'Китай','JP':'Япония','KR':'Республика Корея','KP':'КНДР','IN':'Индия','PK':'Пакистан',
 'BD':'Бангладеш','LK':'Шри-Ланка','NP':'Непал','MN':'Монголия','TH':'Таиланд','VN':'Вьетнам',
 'MY':'Малайзия','SG':'Сингапур','ID':'Индонезия','PH':'Филиппины','MM':'Мьянма','KH':'Камбоджа','LA':'Лаос',
 'TR':'Турция','IR':'Иран','IQ':'Ирак','SY':'Сирия','IL':'Израиль','SA':'Саудовская Аравия',
 'AE':'ОАЭ','QA':'Катар','KW':'Кувейт','JO':'Иордания','LB':'Ливан','YE':'Йемен','OM':'Оман','AF':'Афганистан',
 'EG':'Египет','MA':'Марокко','DZ':'Алжир','TN':'Тунис','LY':'Ливия','SD':'Судан',
 'NG':'Нигерия','ET':'Эфиопия','KE':'Кения','TZ':'Танзания','ZA':'ЮАР','GH':'Гана','CD':'ДР Конго',
 'AU':'Австралия','NZ':'Новая Зеландия','CU':'Куба','DO':'Доминикана','CR':'Коста-Рика',
}
def load_country_en():
    en = {}
    with open(os.path.join(SP, 'countryInfo.txt'), encoding='utf-8') as f:
        for line in f:
            if line.startswith('#'): continue
            c = line.rstrip('\n').split('\t')
            if len(c) > 4 and c[0]: en[c[0]] = c[4]
    return en

# ════════ ПРОХОД A: структура RU.txt (коды регионов/районов + населённые пункты) ════════
print('Читаю RU.txt (структура) …')
adm1_gid, adm2_gid = {}, {}
adm_gids = set()
ru_rows_raw = []   # (pop, gid, name, alt, lat, lon, a1, a2, tz)
with open(os.path.join(SP, 'RU.txt'), encoding='utf-8') as f:
    for line in f:
        c = line.rstrip('\n').split('\t')
        if len(c) < 18: continue
        gid, name, alt = c[0], c[1], c[3]
        fclass, fcode, a1, a2 = c[6], c[7], c[10], c[11]
        if fcode == 'ADM1':
            adm1_gid[a1] = gid; adm_gids.add(gid); continue
        if fcode == 'ADM2':
            adm2_gid[a1 + '.' + a2] = gid; adm_gids.add(gid); continue
        if fclass != 'P': continue
        try: lat = float(c[4]); lon = float(c[5])
        except ValueError: continue
        ru_rows_raw.append((int(c[14]) if c[14] else 0, gid, name, alt, lat, lon, a1, a2, c[17]))
pop_gids = {r[1] for r in ru_rows_raw}
print('  населённых пунктов РФ:', len(ru_rows_raw), '| регионов:', len(adm1_gid), '| районов:', len(adm2_gid))

# ════════ ПРОХОД B: русские альт-имена (двойная оценка) ════════
print('Читаю altnames/RU.txt …')
def better(cur, score, nm):
    return cur is None or score > cur[0] or (score == cur[0] and len(nm) < len(cur[1]))
ru_pop, ru_adm = {}, {}
with open(os.path.join(SP, 'altnames', 'RU.txt'), encoding='utf-8') as f:
    for line in f:
        c = line.rstrip('\n').split('\t')
        if len(c) < 4 or c[2] != 'ru': continue
        gid = c[1]; nm = c[3].strip()
        if not nm: continue
        isPref = len(c) > 4 and c[4] == '1'
        isColl = len(c) > 6 and c[6] == '1'
        isHist = len(c) > 7 and c[7] == '1'
        if gid in adm_gids:                         # регион/район — предпочесть официальную форму
            score = (5 if OFFICIAL.search(nm) else 0) + (2 if isPref else 0) - (3 if isColl else 0) - (3 if isHist else 0)
            if better(ru_adm.get(gid), score, nm): ru_adm[gid] = (score, nm)
        elif gid in pop_gids:                       # населённый пункт — обычная оценка
            score = (2 if isPref else 0) - (1 if isColl else 0) - (1 if isHist else 0)
            if better(ru_pop.get(gid), score, nm): ru_pop[gid] = (score, nm)
ru_pop = {k: v[1] for k, v in ru_pop.items()}
ru_adm = {k: v[1] for k, v in ru_adm.items()}

# имена регионов/районов
region_of, district_of = {}, {}
for a1, gid in adm1_gid.items():
    rn = fix_case(ru_adm.get(gid, ''))
    region_of[a1] = REGION_FIX.get(rn, rn)
for key, gid in adm2_gid.items():
    district_of[key] = fix_case(ru_adm.get(gid, ''))
_susp = sorted(r for r in region_of.values() if r and not OFFICIAL.search(r))
print('  регионы без офиц. суффикса (краткие имена республик/АО/города — это норма):', _susp)

# ════════ Мир (cities5000, кроме РФ) ════════
print('Читаю cities5000.txt + admin1 …')
admin1_en = {}
with open(os.path.join(SP, 'admin1CodesASCII.txt'), encoding='utf-8') as f:
    for line in f:
        c = line.rstrip('\n').split('\t')
        if len(c) >= 2: admin1_en[c[0]] = c[1]
country_en = load_country_en()
def country_name(cc): return COUNTRY_RU.get(cc) or country_en.get(cc) or cc

world_rows = []
with open(os.path.join(SP, 'cities5000.txt'), encoding='utf-8') as f:
    for line in f:
        c = line.rstrip('\n').split('\t')
        if len(c) < 18 or c[8] == 'RU': continue
        try: lat = float(c[4]); lon = float(c[5])
        except ValueError: continue
        a1 = admin1_en.get(c[8] + '.' + c[10], '')
        label = ', '.join(x for x in (a1, country_name(c[8])) if x)
        world_rows.append((int(c[14]) if c[14] else 0, c[1], lat, lon, label, c[17]))
print('  городов мира (≥5000, без РФ):', len(world_rows))

# ════════ Единый список + индексы ════════
zones, admins = {}, {}
def zidx(z):
    if z not in zones: zones[z] = len(zones)
    return zones[z]
def aidx(a):
    if a not in admins: admins[a] = len(admins)
    return admins[a]

rows = []
for pop, gid, name, alt, lat, lon, a1, a2, tz in ru_rows_raw:
    disp = ru_pop.get(gid) or first_cyr(alt) or (name if CYR.search(name) else translit(name))
    parts = []
    d = district_of.get(a1 + '.' + a2)
    if d: parts.append(d)
    r = region_of.get(a1)
    if r: parts.append(r)
    parts.append('Россия')
    rows.append((pop, disp, round(lat*1e4), round(lon*1e4), aidx(', '.join(parts)), zidx(tz)))
for pop, name, lat, lon, label, tz in world_rows:
    rows.append((pop, name, round(lat*1e4), round(lon*1e4), aidx(label), zidx(tz)))

rows.sort(key=lambda x: -x[0])     # крупные города выше
print('Всего записей:', len(rows), '| зон:', len(zones), '| админ-меток:', len(admins))

# ════════ Запись ════════
zones_list = [None]*len(zones)
for z, i in zones.items(): zones_list[i] = z
admins_list = [None]*len(admins)
for a, i in admins.items(): admins_list[i] = a

with open(os.path.join(OUT, 'cities-meta.json'), 'w', encoding='utf-8') as f:
    json.dump({'zones': zones_list, 'admins': admins_list,
               'count': len(rows), 'source': 'GeoNames (CC-BY 4.0)'}, f, ensure_ascii=False)

buf = io.StringIO()
for pop, name, la, lo, ai, zi in rows:
    buf.write('%s\t%d\t%d\t%d\t%d\n' % (name, la, lo, ai, zi))
text = buf.getvalue().encode('utf-8')
with open(os.path.join(OUT, 'cities.txt'), 'wb') as f: f.write(text)
with gzip.open(os.path.join(OUT, 'cities.txt.gz'), 'wb', compresslevel=9) as f: f.write(text)

print('cities-meta.json: %.1f KB' % (os.path.getsize(os.path.join(OUT,'cities-meta.json'))/1024))
print('cities.txt:       %.2f MB' % (os.path.getsize(os.path.join(OUT,'cities.txt'))/1024/1024))
print('cities.txt.gz:    %.2f MB' % (os.path.getsize(os.path.join(OUT,'cities.txt.gz'))/1024/1024))
print('--- пример: регионы (первые 12) ---')
for r in sorted(set(region_of.values()))[:12]: print('  ', r)
