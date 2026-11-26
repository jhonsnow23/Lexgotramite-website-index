"""Static knowledge hub and explicitly human-authorized publication; never used by cron.
Run publication locally on a trusted checkout; review the Git diff before deployment.
"""
import argparse, html, json, re, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import first_article_v50 as engine
import editorial_quality_v50 as editorial
import official_sources_v50 as official
import renewal_intent_v50 as renewal
import publish_next_article as blog
ROOT=Path(__file__).resolve().parents[1]
BASE='/guias/renovaciones-residencia-espana/'
SITE='https://lexgotramite.com'
INVENTORY='guias/published-inventory.json'
START='<!-- LEXGO KNOWLEDGE HUB START -->'; END='<!-- LEXGO KNOWLEDGE HUB END -->'
CATEGORIES={
 'regularizacion_2026':('renovacion-regularizacion-masiva','Renovaciones de la regularización masiva','Opciones para continuar tu residencia tras la regularización extraordinaria.','shield'),
 'arraigo':('renovacion-arraigo','Renovaciones y modificaciones de arraigo','Prórrogas y modificaciones para continuar tu residencia.','refresh'),
 'cuenta_ajena':('renovacion-cuenta-ajena','Renovación de residencia y trabajo por cuenta ajena','Primera renovación, cambios de empleador, plazos y duración.','work'),
 'cuenta_propia':('renovacion-cuenta-propia','Renovación de residencia por cuenta propia','Información para renovar tu autorización como autónomo.','store'),
 'no_lucrativa':('renovacion-residencia-no-lucrativa','Renovación de residencia no lucrativa','Requisitos económicos, seguro médico, documentación y plazos.','home'),
 'menores_no_nacidos':('renovacion-residencia-hijos-menores','Renovación de residencia de hijos menores','Continuidad de las autorizaciones de menores no nacidos en España.','people'),
}
ICONS={'shield':'M12 3 21 7v5c0 5-9 9-9 9S3 17 3 12V7l9-4m-4 9 3 3 5-6','refresh':'M20 7v5h-5M4 17v-5h5M5 10a7 7 0 0 1 12-4l3 6M19 14a7 7 0 0 1-12 4l-3-6','work':'M3 7h18v13H3zM8 7V4h8v3M3 12h18m-11 0v3h4v-3','store':'M3 8l2-4h14l2 4v4H3zm2 4v9h14v-9m-8 9v-6h5v6','home':'M3 11 12 3l9 8M5 10v11h14V10M10 21v-7h4v7','people':'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6m8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6M2 21v-3a6 6 0 0 1 12 0v3m2-7a6 6 0 0 1 6 6v1'}
def esc(s): return html.escape(str(s),quote=True)
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,s): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
def save(p,v): write(p,json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def cat_url(c): return '/guias/'+CATEGORIES[c][0]+'/'
def today(): return datetime.now(ZoneInfo('Europe/Madrid')).date().isoformat()
def inventory(root):
    p=root/INVENTORY
    rows=read(p) if p.exists() else []
    for r in rows:
        if r['status']!='PUBLISHED' or r['category'] not in CATEGORIES or r['content_type'] not in ('KNOWLEDGE_ARTICLE','WEEKLY_BLOG'):raise ValueError('Public inventory contains invalid/unpublished content')
    return rows

def links(rows):
    return ''.join(f'<li><a href="{esc(r["url"])}">{esc(r["title"])}</a><p>{esc(r["description"])}</p><small>{esc(r["published_at"])}</small></li>' for r in rows)
def category_cards(rows):
    cards=[]
    for c,(_,name,desc,icon) in CATEGORIES.items():
        n=sum(r['category']==c and r['content_type']=='KNOWLEDGE_ARTICLE' for r in rows)
        link=f'<a href="{cat_url(c)}">Consultar guía <span aria-hidden="true">→</span></a><small>{n} {"artículo" if n==1 else "artículos"}</small>' if n else '<small>Próximamente: información en preparación</small>'
        cards.append(f'<article class="lg-guide-card"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="{ICONS[icon]}"/></svg><h3>{esc(name)}</h3><p>{esc(desc)}</p><div class="lg-guide-action">{link}</div></article>')
    return '<div class="lg-guide-grid">'+''.join(cards)+'</div>'
def home_section(rows):
    recent=sorted((r for r in rows if r['content_type']=='KNOWLEDGE_ARTICLE'),key=lambda r:r['published_at'],reverse=True)[:6]
    latest='<h3 class="lg-guide-subtitle">Últimas guías y artículos sobre renovaciones</h3><ul class="lg-guide-links">'+links(recent)+'</ul>' if recent else ''
    return START+'\n<section id="guias-renovacion" class="lg-guide-section" aria-labelledby="lg-guide-title"><div class="lg-guide-wrap"><div class="lg-guide-intro"><span class="lg-guide-label">Información y guías de extranjería</span><h2 id="lg-guide-title">Guía de renovaciones de residencia en España</h2><p>¿Tu autorización de residencia está a punto de caducar? En Lex Go Trámite te ayudamos a entender tus opciones para continuar viviendo legalmente en España. Consulta información sobre renovaciones, prórrogas, modificaciones, requisitos, documentación y plazos.</p></div>'+category_cards(rows)+latest+f'<p class="lg-guide-all"><a href="{BASE}">Ver todas las guías de renovación <span aria-hidden="true">→</span></a></p></div></section>\n'+END

def page(title,desc,url,body,index=True):
    canonical=SITE+url
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | Lex Go Trámite</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="{'index,follow' if index else 'noindex,follow'}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><link rel="icon" href="/favicon.ico"><link rel="stylesheet" href="/guias/knowledge.css"></head><body class="lg-guide-page"><main class="lg-guide-wrap"><nav aria-label="Ruta de navegación"><a href="/">Inicio</a> · <a href="{BASE}">Guías de renovación</a> · <a href="/blog/">Blog</a></nav><h1>{esc(title)}</h1><p>{esc(desc)}</p>{body}<p class="lg-guide-all"><a href="/#cita">Reservar una cita</a></p></main><script src="/cookies.js"></script></body></html>'''

def add_sitemap(root,urls):
    path=root/'sitemap.xml'; text=path.read_text(encoding='utf-8'); assert text.count('</urlset>')==1
    entries=[]
    for url in sorted(set(urls)):
        loc=SITE+url
        if f'<loc>{loc}</loc>' not in text:entries.append(f'  <url>\n    <loc>{esc(loc)}</loc>\n    <lastmod>{today()}</lastmod>\n  </url>\n')
    if entries:write(path,text.replace('</urlset>',''.join(entries)+'</urlset>'))

def render_hub(root=ROOT):
    rows=inventory(root); path=root/'index.html'; text=path.read_text(encoding='utf-8'); block=home_section(rows)
    if START in text:
        if text.count(START)!=1 or text.count(END)!=1:raise ValueError('Ambiguous hub markers')
        text=text[:text.index(START)]+block+text[text.index(END)+len(END):]
    else:
        marker='<!-- Reseñas Google -->'; assert text.count(marker)==1 and text.index('id="galeria"')<text.index(marker)<text.index('id="resenas"')
        text=text.replace(marker,block+'\n'+marker,1)
    css='<link rel="stylesheet" href="/guias/knowledge.css">'
    if css not in text:text=text.replace('</head>',css+'\n</head>',1)
    write(path,text)
    published=[r for r in rows if r['content_type']=='KNOWLEDGE_ARTICLE']; weekly=[r for r in rows if r['content_type']=='WEEKLY_BLOG']; urls=[]
    body=category_cards(rows)+('<h2>Últimos artículos</h2><ul class="lg-guide-links">'+links(published[::-1])+'</ul>' if published else '<p>Estamos preparando nuevas guías de renovación. Mientras tanto, puedes contactar con nosotros si necesitas revisar tu situación.</p>')
    if weekly:body+='<h2>En nuestro blog</h2><ul class="lg-guide-links">'+links(weekly[::-1])+'</ul>'
    write(root/(BASE.strip('/')+'/index.html'),page('Guía de renovaciones de residencia en España','Información organizada por tipo de autorización.',BASE,body,bool(published)))
    if published:urls.append(BASE)
    for c,(_,title,desc,_) in CATEGORIES.items():
        items=[r for r in published if r['category']==c]; related=[r for r in weekly if r['category']==c]
        if not items:continue
        body='<h2>Preguntas y artículos</h2><ul class="lg-guide-links">'+links(items[::-1])+'</ul>'
        for r in items:
            if r.get('inline_html'):body+=f'<section id="{esc(r["slug"])}" class="lg-guide-answer"><h2>{esc(r["title"])}</h2>{r["inline_html"]}</section>'
        if related:body+='<h2>Artículos del blog</h2><ul class="lg-guide-links">'+links(related[::-1])+'</ul>'
        write(root/(cat_url(c).strip('/')+'/index.html'),page(title,desc,cat_url(c),body));urls.append(cat_url(c))
    if urls:add_sitemap(root,urls)

def approved_source(folder):
    folder=Path(folder); a=read(folder/'article.json'); m=read(folder/'article_metadata.json'); r=read(folder/'legal_review.json'); d=read(folder/'decision.json')
    if not (a['simulated'] is False and a['automated_review_passed'] is True and a['publication_allowed'] is False and r['simulated'] is False and r['passed'] is True and r['verdict']['approved'] is True and d['result']=='REVIEW_READY' and d['simulated'] is False):raise ValueError('Not a real independently reviewed draft')
    stripped={k:v for k,v in a.items() if k not in ('content_hash','automated_review_passed','simulated','legal_accuracy_certified')}
    if engine.digest(stripped)!=a['content_hash'] or r['article_hash']!=a['content_hash']:raise ValueError('Reviewed article content hash mismatch')
    v=r['verdict']; expected_claims={p['claim_id'] for s in a['sections'] for p in s['paragraphs']}
    checks=v.get('claim_checks',[])
    if (v.get('defects') or any(v.get(k) is not True for k in engine.CHECKS) or len(checks)!=len(expected_claims)
        or {x.get('claim_id') for x in checks}!=expected_claims or any(x.get('supported') is not True for x in checks)
        or any(x.get('resolved') is not True for x in v.get('prior_defect_checks',[]))):raise ValueError('Independent review is incomplete or inconsistent')
    if r.get('blocking_gap_ids') and (set(r['blocking_gap_ids'])!={x.get('gap_id') for x in v.get('blocking_gap_checks',[])} or any(x.get('resolution')=='STILL_BLOCKING' for x in v.get('blocking_gap_checks',[]))):raise ValueError('Unresolved material gap in review')
    engine.plain(a['title']);gate=renewal.assess(a['title']);cat=m['category']
    if gate['excluded'] or gate['business_category']!=cat or m['topic']!=a['title']:raise ValueError('Outside renewal scope or inconsistent metadata')
    kind='WEEKLY_BLOG' if m.get('weekly_context') is not None and m.get('origin')=='EDITORIAL_SYNTHESIS' else 'KNOWLEDGE_ARTICLE'
    if m.get('content_type',kind)!=kind:raise ValueError('Conflicting content type')
    if kind=='WEEKLY_BLOG' and a['article_type']!='information':raise ValueError('Wrong article type for weekly blog')
    # Approval is bound to the exact article, review, metadata, decision and destination.
    approval=engine.digest({'article':a,'review':r,'metadata':m,'decision':d,'content_type':kind})
    return a,m,kind,approval

def body_html(a):
    def citations(rows):
        out=[]
        for c in rows:
            if not official.allowed(c['url']):raise ValueError('Citation outside official allowlist')
            out.append(f'<a href="{esc(c["url"])}">{esc(c.get("label") or c.get("title") or "Fuente oficial")}</a>')
        return '; '.join(dict.fromkeys(out))
    parts=[f'<p>{esc(a["introduction"])}</p>'] if a['introduction'] else []
    for i,s in enumerate(a['sections']):
        parts.append('<section>')
        if not (i==0 and a.get('intro_claim')):parts.append(f'<h2>{esc(s["heading"])}</h2>')
        for p in s['paragraphs']:
            parts.append(f'<p>{esc(editorial.join_fields(p["text"],p["conditions"],p["exceptions"]))}</p><p class="lg-guide-source">Fuente: {citations(p["citations"])}</p>')
        parts.append('</section>')
    if any(x['text'] for x in a['limitations']):
        parts.append('<h2>Qué debes comprobar en tu caso</h2>')
        for x in a['limitations']:
            if x['text']:parts.append(f'<p>{esc(x["text"])} {citations(x["citations"])}</p>')
    if a.get('disclaimer'):parts.append(f'<p class="lg-guide-source">{esc(a["disclaimer"])}</p>')
    return '\n'.join(parts)

def publish(folder,approve,root=ROOT,*,authorization=None):
    a,m,kind,expected=approved_source(folder)
    if approve!=expected:raise ValueError('Exact reviewed content approval hash required')
    if authorization is not None:
        import os
        if (os.environ.get('LEXGO_AUTOPUBLISH_ENABLED')!='true' or authorization.get('policy')!='v66-autonomous-1'
            or authorization.get('state')!='AUTOMATED_PUBLICATION_AUTHORIZED' or authorization.get('human_approved') is not False
            or authorization.get('approval_hash')!=expected or authorization.get('article_hash')!=a['content_hash']
            or authorization.get('content_type')!=kind):raise ValueError('Invalid automated publication authorization')
    rows=inventory(root); slug=engine.seo.proposed_slug(a['title']); cat=m['category']; dt=today()
    if not re.fullmatch(r'[a-z0-9-]+',slug) or any(r['content_hash']==a['content_hash'] or editorial.normalized(r['title'])==editorial.normalized(a['title']) for r in rows):raise ValueError('Duplicate content or invalid slug')
    description=m.get('meta_description') or engine.editorial_metadata(a,m)['meta_description']; engine.plain(description); html_body=body_html(a); words=sum(len(editorial.join_fields(p['text'],p['conditions'],p['exceptions']).split()) for s in a['sections'] for p in s['paragraphs'])
    if authorization is not None:
        # Neutral metadata avoids omitting a material exception from a short snippet.
        description='Información sobre '+a['title']+'.'
        html_body='<div data-lexgo-content-hash="'+esc(a['content_hash'])+'">'+html_body+'<p class="lg-guide-source">Información general elaborada con fuentes oficiales y comprobaciones automatizadas. No sustituye una valoración profesional de tu caso.</p></div>'
    related=[r for r in rows if r['category']==cat and r['content_type']=='KNOWLEDGE_ARTICLE'][-6:]
    # Only public existing destinations; append navigation, never alter legal prose.
    related_html=('<h2>Información relacionada</h2><ul class="lg-guide-links">'+links(related)+'</ul>') if related else ''
    row={'content_type':kind,'category':cat,'title':a['title'],'slug':slug,'description':description,'content_hash':a['content_hash'],'approval_hash':expected,'status':'PUBLISHED','published_at':dt,'word_count':words,'origin':m.get('origin'),'primary_search_query':m.get('primary_search_query')}
    if authorization is not None:
        row.update(publication_authorization=authorization,source_run_id=authorization['source_run_id'],publication_policy=authorization['policy'],human_approved=False)
    if kind=='KNOWLEDGE_ARTICLE':
        if words<150:
            row.update(url=cat_url(cat)+'#'+slug,inline_html=html_body)
        else:
            url=cat_url(cat)+slug; target=root/(url.strip('/')+'.html')
            if target.exists():raise ValueError('Existing article must not be overwritten')
            row['url']=url;write(target,page(a['title'],description,url,html_body+f'<p><a href="{cat_url(cat)}">{esc(CATEGORIES[cat][1])}</a></p>'+related_html));add_sitemap(root,[url])
    else:
        # Reuse the existing blog renderer and indexing mechanism, preserving
        # all reviewed legal paragraphs/citations instead of flattening them.
        url='/blog/'+slug; target=root/(url.strip('/')+'.html')
        if target.exists():raise ValueError('Existing blog post must not be overwritten')
        if words<150:raise ValueError('Too little substantive information for weekly blog; use a guide entry after new review')
        row['url']=url
        draft={'title':a['title'],'description':description,'slug':slug,'intro':'','category':CATEGORIES[cat][1],'sections':[]}
        rendered=blog.render_article(draft,dt); needle='<div class="mt-10 space-y-10">\n      \n    </div>'
        if needle not in rendered:raise ValueError('Blog renderer template changed')
        rendered=rendered.replace(needle,'<div class="mt-10 space-y-6 lg-guide-blog">'+html_body+related_html+(f'<p><a href="{cat_url(cat)}">{esc(CATEGORIES[cat][1])}</a></p>' if related else '')+'</div>',1)
        rendered=rendered.replace('</head>','<link rel="stylesheet" href="/guias/knowledge.css"></head>',1)
        write(target,rendered); add_sitemap(root,[url])
        # Existing blog helpers use module-level paths; local root is explicit.
        blog.ROOT=root;blog.BLOG_DIR=root/'blog';blog.STATE_FILE=root/'publish_state.json';blog.BLOG_INDEX_FILE=root/'blog/index.html';blog.HOME_FILE=root/'index.html'
        st=blog.load_state();st['published'].append(slug);st['published_dates'][slug]=dt;st['last_published']=dt;blog.save_state(st);blog.update_blog_index();blog.update_home_blog_section()
    rows.append(row);save(root/INVENTORY,rows);render_hub(root);return row

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True);sub.add_parser('render')
    x=sub.add_parser('inspect');x.add_argument('folder');x=sub.add_parser('publish');x.add_argument('folder');x.add_argument('--approve-hash',required=True)
    a=p.parse_args()
    if a.cmd=='render':render_hub()
    elif a.cmd=='inspect':
        article,meta,kind,h=approved_source(a.folder);print(json.dumps({'title':article['title'],'content_type':kind,'approval_hash':h,'human_review_required':True},ensure_ascii=False,indent=2))
    else:print(json.dumps(publish(a.folder,a.approve_hash),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
