"""Manual-only trusted Actions artifact inspection and website patch preparation.
Never push, deploy, publish to GitHub, or change the source run.
"""
import json, os, re, subprocess, sys, shutil, urllib.request
from pathlib import Path
import knowledge_hub_v50 as hub
from seo_v50 import ArtifactRedirect
SOURCES={'daily':('lexgo-seo-v50.yml','lexgo-v50-results','KNOWLEDGE_ARTICLE'),
         'weekly':('lexgo-weekly-blog-v50.yml','lexgo-v50-weekly-blog-results','WEEKLY_BLOG'),
         'first_article':('lexgo-first-article-v50.yml','lexgo-v50-first-article-results','KNOWLEDGE_ARTICLE')}

def validate_run():
    rid=os.environ['SOURCE_RUN_ID'];repo=os.environ['GITHUB_REPOSITORY']; kind=os.environ['SOURCE_TYPE']
    if not re.fullmatch(r'\d+',rid) or not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):raise ValueError('Invalid source run ID or repository')
    file,artifact,_=SOURCES[kind]
    req=urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs/{rid}',headers={'Authorization':'Bearer '+os.environ['GH_HISTORY_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'LexGo-v65-publication'})
    with urllib.request.build_opener(ArtifactRedirect()).open(req,timeout=30) as r:data=json.load(r)
    if data['head_branch']!='main' or data['status']!='completed' or data['path'].split('@',1)[0]!='.github/workflows/'+file or data['head_repository']['full_name'].lower()!=repo.lower():raise ValueError('Source must be a completed trusted main-branch generation run')
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('artifact='+artifact+'\n')

def prepare(source,output,kind,approval):
    source=Path(source);output=Path(output); output.mkdir(parents=True,exist_ok=True)
    articles=list(source.rglob('article.json'))
    if len(articles)!=1:raise ValueError('Expected exactly one real reviewed article')
    folder=articles[0].parent
    a,m,actual,h=hub.approved_source(folder)
    if actual!=SOURCES[kind][2]:raise ValueError('Article destination disagrees with source workflow')
    hub.save(output/'approval-preview.json',{'title':a['title'],'content_type':actual,'approval_hash':h,'human_review_required':True,'publication_allowed':False,'mode':'PATCH_PREPARATION' if approval else 'INSPECT_ONLY'})
    shutil.copyfile(folder/'article.md',output/'article-for-human-review.md');shutil.copyfile(folder/'legal_review.json',output/'legal_review.json')
    if not approval:return
    if approval!=h:raise ValueError('Human approval hash mismatch')
    root=hub.ROOT
    if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():raise ValueError('Publication preparation requires clean checkout')
    result=hub.publish(folder,approval,root)
    # Only website files created by the explicit manual command are packaged.
    raw=subprocess.check_output(['git','ls-files','--modified','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
    files=sorted(set(x for x in raw if x))
    if not files or any(not (x in ('index.html','sitemap.xml','publish_state.json') or x.startswith(('guias/','blog/')) and x.endswith(('.html','.json'))) for x in files):raise ValueError('Unexpected publication patch file')
    subprocess.run(['git','add','-N','--',*files],cwd=root,check=True)
    (output/'publication.patch').write_bytes(subprocess.check_output(['git','diff','--binary','HEAD','--',*files],cwd=root))
    for name in files:
        target=output/'WEBSITE-FILES'/name; target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
    hub.save(output/'prepared-publication.json',{'article':result,'files':files,'approval_hash':h,'live_publication_performed':False,'publication_allowed':False,'next_step':'Review the website files and commit manually; no push or deployment was performed.'})

if __name__=='__main__':
    if sys.argv[1]=='validate-run':validate_run()
    elif sys.argv[1]=='prepare':prepare(sys.argv[2],sys.argv[3],os.environ['SOURCE_TYPE'],os.environ.get('APPROVAL_HASH',''))
    else:raise SystemExit('Unknown command')
